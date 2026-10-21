"""Turn the two files into a package for the bank reviewer: matches, flags, figures and the one-page summary.

Everything here is plain rules and arithmetic (no model calls), so the same input always gives the same
output and every number can be traced to rows.
"""
import datetime as dt
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from .ingest_invoices import read_invoices
from .ingest_statement import read_statement
from .matching import TOL, match_all
from .names import CustomerRegistry, normalize

INV_FILE, STMT_FILE = "invoices_12m.xlsx", "bank_statement_12m.pdf"
BUCKETS = [("1-30 days", 1, 30), ("31-60 days", 31, 60), ("61-90 days", 61, 90), ("Over 90 days", 91, 10**6)]
NON_SALES = {"loan": "Bank loan", "owner_injection": "Owner capital", "own_account_transfer": "Own-account transfer", "supplier_refund": "Supplier refund"}


@dataclass
class Flag:
    id: str
    type: str
    severity: str                 # blocking | warning | note
    title: str
    message: str
    amount: int | None = None
    invoice_rows: list = field(default_factory=list)
    txn_ids: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    resolved: dict | None = None  # {"note": ..., "by": ..., "at": ...}


class Analysis:
    def __init__(self, invoice_path: str, statement_path: str):
        self.invoices = read_invoices(invoice_path)
        self.registry = CustomerRegistry(self.invoices)
        self.statement = read_statement(statement_path)
        self.txns = self.statement.txns
        self.tx_by_id = {t.id: t for t in self.txns}
        m = re.search(r"(\d{2} \w{3} \d{4}) to (\d{2} \w{3} \d{4})", self.statement.period or "")
        self.start = dt.datetime.strptime(m.group(1), "%d %b %Y").date() if m else dt.date(2025, 10, 1)
        self.end = dt.datetime.strptime(m.group(2), "%d %b %Y").date() if m else dt.date(2026, 9, 30)
        self.result = match_all(self.invoices, self.txns, self.registry)
        self._index()
        self._balance_check()
        self._circular()
        self._flags()
        self._metrics()

    # ------------------------------------------------------------------ indexes
    def _index(self):
        self.inv_by_no: dict[str, object] = {}
        self.skipped = self.result.skipped_invoices
        for i in self.invoices:
            if i.kind == "Invoice" and i.row not in self.skipped:
                self.inv_by_no.setdefault(i.no, i)
        self.matches_by_inv: dict[str, list] = defaultdict(list)
        self.matches_by_txn: dict[str, list] = defaultdict(list)
        for m in self.result.matches:
            self.matches_by_inv[m.invoice_no].append(m)
            self.matches_by_txn[m.txn_id].append(m)
        self.credit_by_orig: dict[str, int] = defaultdict(int)
        for i in self.invoices:
            if i.kind == "Credit Note" and i.orig_no and i.total:
                self.credit_by_orig[i.orig_no] += i.total

    def want(self, inv) -> int:
        return (inv.total or 0) + self.credit_by_orig.get(inv.no, 0)

    def paid(self, inv) -> int:
        return sum(m.applied for m in self.matches_by_inv.get(inv.no, []))

    def status(self, inv) -> str:
        if inv.row in self.skipped:
            return "not used (duplicate)"
        if inv.kind == "Credit Note":
            return "credit note"
        p, w = self.paid(inv), self.want(inv)
        return "paid" if p >= w - TOL else ("partly paid" if p > 0 else "unpaid")

    def last_payment(self, inv):
        ms = self.matches_by_inv.get(inv.no, [])
        return max((self.tx_by_id[m.txn_id].date for m in ms), default=None)

    def due(self, inv):
        return inv.due or (inv.date + dt.timedelta(days=30) if inv.date else None)

    # ------------------------------------------------------------------ statement checks
    def _balance_check(self):
        """Walk the statement. A printed balance that disagrees with the running total is an edited or damaged
        page. A page we cannot read hides some lines; we report how much money moved through it."""
        self.balance_issues, self.gaps = [], []
        prev_true = self.statement.opening_balance
        prev_page = 0
        offset_span = None
        for t in self.txns:
            if t.page - prev_page > 1 and prev_page:       # pages in between had no text
                unread = list(range(prev_page + 1, t.page))
                implied = t.balance_printed - t.credit + t.debit      # balance before this line, as printed
                self.gaps.append({"pages": unread, "moved": implied - prev_true, "before": prev_true, "after": implied,
                                  "first_txn": t.id})
                prev_true = implied
            true_bal = prev_true + t.credit - t.debit
            off = t.balance_printed - true_bal
            if off and offset_span is None:
                offset_span = {"start": t, "offset": off, "pages": {t.page}}
            elif off and offset_span:
                offset_span["pages"].add(t.page)
            elif not off and offset_span:
                self.balance_issues.append({**offset_span, "end": t})
                offset_span = None
            prev_true, prev_page = true_bal, t.page
        if offset_span:
            self.balance_issues.append({**offset_span, "end": None})
        self.lowest_balance = min((t.balance_printed for t in self.txns), default=0)
        self.closing_balance = self.txns[-1].balance_printed if self.txns else 0

    def _circular(self):
        """Money that comes in from a customer and goes back out to the same name within a few days."""
        self.circular_invoices: set[str] = set()
        self.circular_pairs = []
        outs = [t for t in self.txns if t.debit and t.category in ("transfer_out", "refund_to_customer")]
        for t in outs:
            cid = None
            for part in re.split(r"\s+-\s+", re.sub(r"^(TRANSFER TO|REFUND TO CUSTOMER)\s*", "", t.description, flags=re.I)):
                cid, how = self.registry.resolve(part.strip(" -"))
                if cid:
                    break
            if not cid or t.category == "refund_to_customer":
                continue
            for d in self.txns:
                if d.credit and d.category == "customer_receipt" and self.result.deposit_customer.get(d.id, (None,))[0] == cid \
                        and 0 <= (t.date - d.date).days <= 5 and t.debit >= 0.9 * d.credit and t.debit <= 1.02 * d.credit:
                    self.circular_pairs.append((d, t, cid))
                    for m in self.matches_by_txn.get(d.id, []):
                        self.circular_invoices.add(m.invoice_no)
                    break

    # ------------------------------------------------------------------ flags
    def _flags(self):
        F: list[Flag] = []
        add = lambda *a, **k: F.append(Flag(f"F{len(F) + 1:02d}", *a, **k))
        inv_rows = [i for i in self.invoices if i.kind == "Invoice"]
        # blocking ------------------------------------------------------
        rep = [i for i in inv_rows if self.skipped.get(i.row) == "repeated row"]
        if rep:
            add("duplicate_invoice_rows", "blocking", f"{len(rep)} invoice rows appear twice",
                "The same invoice number is listed twice with identical details. We count each only once, but the file should be corrected before it goes to a bank.",
                amount=sum(i.total for i in rep), invoice_rows=[i.row for i in rep] + [self.inv_by_no[i.no].row for i in rep])
        reis = [i for i in inv_rows if str(self.skipped.get(i.row, "")).startswith("same customer")]
        if reis:
            add("possible_reissued_invoice", "blocking", f"{len(reis)} invoices look like a re-issue of another invoice",
                "Same customer, same date and same amount as another invoice, under a different number. Only one was paid. If both are counted, revenue is overstated.",
                amount=sum(i.total for i in reis), invoice_rows=[i.row for i in reis] + [self.inv_by_no[re.search(r"INV-\d{4}-\d{4}", self.skipped[i.row]).group(0)].row for i in reis])
        for g in self.gaps:
            add("unreadable_statement_page", "blocking", f"Statement page {', '.join(map(str, g['pages']))} cannot be read",
                f"The page is an image with no readable text, so its lines are missing. The balance moves by SAR {abs(g['moved']) / 100:,.2f} "
                f"({'up' if g['moved'] > 0 else 'down'}) across the missing page. Payments on it show up as unpaid invoices until a clear copy is supplied.",
                amount=abs(g["moved"]), pages=g["pages"])
        for b in self.balance_issues:
            s = b["start"]
            add("balance_mismatch", "blocking", f"Balance does not add up on statement page {', '.join(map(str, sorted(b['pages'])))}",
                f"From line {s.line} on page {s.page} the printed balance is SAR {abs(b['offset']) / 100:,.2f} {'higher' if b['offset'] > 0 else 'lower'} than the lines above it add up to"
                + (f", and it returns to the correct value on page {b['end'].page}." if b["end"] else ".") + " This can mean the page was edited.",
                amount=abs(b["offset"]), pages=sorted(b["pages"]), txn_ids=[s.id])
        if self.circular_pairs:
            names = sorted({self.registry.display(c) for _, _, c in self.circular_pairs})
            add("circular_money", "blocking", f"{len(self.circular_pairs)} payments go back out to the customer who paid",
                f"{', '.join(names)} pays an invoice and, within 5 days, almost the same amount is sent back to the same name. This looks like money going in a circle, not real sales. We leave these invoices out of confirmed revenue.",
                amount=sum(d.credit for d, _, _ in self.circular_pairs),
                txn_ids=[x.id for d, t, _ in self.circular_pairs for x in (d, t)],
                invoice_rows=[self.inv_by_no[n].row for n in self.circular_invoices if n in self.inv_by_no])
        # warnings ------------------------------------------------------
        nums = sorted((i.no for i in inv_rows))
        gap_nos = self._number_gaps()
        if gap_nos:
            add("invoice_number_gap", "warning", f"{len(gap_nos)} invoice numbers are missing",
                "The invoice numbers run in sequence, but these numbers never appear: " + ", ".join(gap_nos) + ". They may be cancelled invoices or sales left out of the file.",
                invoice_rows=[])
        no_due = [i for i in inv_rows if i.due is None and i.row not in self.skipped]
        if no_due:
            add("missing_due_date", "warning", f"{len(no_due)} invoices have no due date",
                "We assumed 30 days from the invoice date for the overdue figures.", invoice_rows=[i.row for i in no_due])
        no_vat = [i for i in self.invoices if not i.vat_no]
        if no_vat:
            add("missing_customer_vat", "warning", f"{len(no_vat)} rows have no customer VAT number",
                "We matched them to a customer by name. Check these rows against the customer's VAT registration.", invoice_rows=[i.row for i in no_vat])
        bad_math = [i for i in self.invoices if i.kind == "Invoice" and i.net and i.vat is not None and i.total is not None
                    and (abs(i.net + i.vat - i.total) > 1 or abs(i.vat - round(i.net * 0.15)) > 2)]
        if bad_math:
            add("vat_or_total_wrong", "warning", f"{len(bad_math)} invoices have the wrong VAT or total",
                "Either the VAT is not 15% of the net amount, or the total is not net plus VAT.", invoice_rows=[i.row for i in bad_math])
        cn_un = [i for i in self.invoices if i.kind == "Credit Note" and not i.orig_no]
        if cn_un:
            add("credit_note_unlinked", "warning", f"{len(cn_un)} credit notes do not say which invoice they correct",
                "We cannot tell which sale was reduced, so we cannot check the customer's payment against it.", amount=sum(i.total for i in cn_un), invoice_rows=[i.row for i in cn_un])
        self.month_receipts = self._month_receipts()
        thin = [m for m, v in self.month_receipts.items() if v["invoiced"] and v["receipts"] < 0.15 * v["invoiced"] * 1.15]
        for m in thin:
            v = self.month_receipts[m]
            add("month_without_customer_payments", "warning", f"Almost no customer payments in {m}",
                f"Invoices of SAR {v['invoiced'] / 100:,.0f} were issued in {m}, but only SAR {v['receipts'] / 100:,.0f} of customer payments arrived that month. "
                "Most payments due in the month appear in the following month. Ask the business why.",
                amount=v["receipts"], txn_ids=[t.id for t in self.txns if t.category == "customer_receipt" and t.date.strftime("%Y-%m") == m])
        overdue90 = [i for i in self.inv_by_no.values() if self._overdue_days(i) > 90]
        if overdue90:
            add("unpaid_over_90_days", "warning", f"{len(overdue90)} invoices are more than 90 days overdue",
                "No payment was found for them. They may be disputed or uncollectable.",
                amount=sum(self.want(i) - self.paid(i) for i in overdue90), invoice_rows=[i.row for i in overdue90])
        if self.result.unmatched:
            tot = sum(t.credit for t in self.result.unmatched)
            early = sum(1 for t in self.result.unmatched if t.date < self.start + dt.timedelta(days=62))
            add("unexplained_deposits", "warning", f"{len(self.result.unmatched)} customer deposits match no invoice",
                f"{early} of them arrived in the first two months, which fits payment of invoices issued before this period. "
                "They are real customer money, but we cannot tie them to this package.", amount=tot, txn_ids=[t.id for t in self.result.unmatched])
        low = [m for m in self.result.matches if m.confidence == "low"]
        if low:
            add("low_confidence_matches", "warning", f"{len(low)} matches are weak and need a person's check",
                "The customer name on the deposit was not recognised, so we matched on the amount alone.", txn_ids=sorted({m.txn_id for m in low}))
        # notes ---------------------------------------------------------
        other = [t for t in self.txns if t.credit and t.category in NON_SALES]
        if other:
            add("non_sales_deposits", "note", f"{len(other)} deposits are not sales",
                "Loan, owner money, transfers from the owner's own account and supplier refunds. They are left out of revenue and customer receipts.",
                amount=sum(t.credit for t in other), txn_ids=[t.id for t in other])
        over = [m for m in self.result.matches if m.method == "overpayment" or "more than the invoice" in m.note]
        if over:
            add("overpayments", "note", f"{len(over)} customers paid more than the invoice",
                "The extra amount is probably a balance carried to the next invoice.", txn_ids=sorted({m.txn_id for m in over}))
        variants = [c for c in self.registry.by_id.values() if len(c["variants"]) > 1]
        if variants:
            add("customer_name_variants", "note", f"{len(variants)} customers appear under several spellings",
                "Arabic or English, with or without \"Co.\", extra spaces. We merged them using the VAT number: " + "; ".join(self.registry.display(c["id"]) for c in variants) + ".")
        fixed = [i for i in self.invoices if i.notes]
        if fixed:
            add("values_repaired", "note", f"{sum(len(i.notes) for i in fixed)} values were stored as text and read correctly",
                "Dates written as text or with Arabic-Indic digits, and amounts with thousands commas stored as text.", invoice_rows=[i.row for i in fixed])
        self.flags = F
        self.flag_by_id = {f.id: f for f in F}

    def _number_gaps(self):
        by_year: dict[str, list[int]] = defaultdict(list)
        seq = []
        for i in self.invoices:
            m = re.fullmatch(r"INV-(\d{4})-(\d{4})", i.no)
            if i.kind == "Invoice" and m:
                seq.append((int(m.group(2)), m.group(1)))
        have = {s for s, _ in seq}
        year_at = {s: y for s, y in seq}
        out = []
        for n in range(min(have), max(have) + 1):
            if n not in have:
                nxt = min(s for s in have if s > n)
                out.append(f"INV-{year_at[nxt]}-{n:04d}")
        return out

    def _overdue_days(self, inv) -> int:
        d = self.due(inv)
        if not d or self.status(inv) in ("paid",) or inv.no in self.circular_invoices:
            return 0
        if self.want(inv) - self.paid(inv) <= TOL:
            return 0
        return (self.end - d).days

    def _month_receipts(self):
        out = {}
        for i in self.invoices:
            if i.kind == "Invoice" and i.date and i.row not in self.skipped:
                out.setdefault(i.date.strftime("%Y-%m"), {"invoiced": 0, "receipts": 0})["invoiced"] += i.net or 0
        circ_dep = {d.id for d, _, _ in self.circular_pairs}
        for t in self.txns:
            if t.category == "customer_receipt" and t.id not in circ_dep:
                out.setdefault(t.date.strftime("%Y-%m"), {"invoiced": 0, "receipts": 0})["receipts"] += t.credit
        return dict(sorted(out.items()))

    # ------------------------------------------------------------------ headline numbers
    def _metrics(self):
        inv_all = [i for i in self.invoices if i.kind == "Invoice" and i.net is not None]
        used = [i for i in inv_all if i.row not in self.skipped]
        rep = [i for i in inv_all if self.skipped.get(i.row) == "repeated row"]
        reis = [i for i in inv_all if i.row in self.skipped and i not in rep]
        cns = [i for i in self.invoices if i.kind == "Credit Note" and i.net is not None]
        circ = [i for i in used if i.no in self.circular_invoices]
        self.bridge = [
            {"key": "listed", "label": "Invoiced, as listed in the file", "value": sum(i.net for i in inv_all)},
            {"key": "repeated", "label": "Rows that appear twice", "value": -sum(i.net for i in rep), "flag": "duplicate_invoice_rows"},
            {"key": "reissued", "label": "Invoices that look re-issued", "value": -sum(i.net for i in reis), "flag": "possible_reissued_invoice"},
            {"key": "credit_notes", "label": "Credit notes", "value": sum(i.net for i in cns)},
        ]
        adjusted = sum(b["value"] for b in self.bridge)
        self.bridge.append({"key": "adjusted", "label": "Invoiced revenue after corrections", "value": adjusted, "total": True})
        self.bridge.append({"key": "circular", "label": "Invoices paid by money that goes back out", "value": -sum(i.net for i in circ), "flag": "circular_money"})
        base = adjusted - sum(i.net for i in circ)
        self.bridge.append({"key": "clean", "label": "Revenue from genuine customers", "value": base, "total": True})
        confirmed = 0.0
        for i in used:
            if i.no in self.circular_invoices:
                continue
            w = self.want(i)
            if w > 0:
                confirmed += (i.net or 0) * min(1.0, self.paid(i) / w)
        # remove credit notes proportionally: confirmed is measured on invoices only, so compare with invoice revenue
        inv_rev = sum(i.net for i in used if i.no not in self.circular_invoices)
        self.bridge.append({"key": "confirmed", "label": "Of which matched to bank deposits", "value": int(confirmed)})
        self.invoice_revenue_clean = inv_rev
        self.confirmed_net = int(confirmed)
        # collection of invoices that were due by the end of the period
        due_set = [i for i in used if i.no not in self.circular_invoices and self.due(i) and self.due(i) <= self.end]
        due_amt = sum(self.want(i) for i in due_set)
        due_paid = sum(min(self.paid(i), self.want(i)) for i in due_set)
        self.collection = {"due_amount": due_amt, "paid": due_paid, "rate": due_paid / due_amt if due_amt else 0, "count": len(due_set)}
        # concentration (merged customers, genuine revenue)
        rev_by_c: dict[str, int] = defaultdict(int)
        for i in used:
            if i.no not in self.circular_invoices:
                rev_by_c[i.customer_id] += i.net
        for i in cns:
            if i.orig_no in self.inv_by_no:
                rev_by_c[self.inv_by_no[i.orig_no].customer_id] += i.net
        tot = sum(rev_by_c.values())
        ranked = sorted(rev_by_c.items(), key=lambda kv: -kv[1])
        self.customers = [{"id": c, "name": self.registry.display(c), "revenue": v, "share": v / tot if tot else 0} for c, v in ranked]
        self.top5_share = sum(c["share"] for c in self.customers[:5])
        # days to pay
        rows = []
        for i in used:
            if self.status(i) == "paid" and i.no not in self.circular_invoices:
                lp = self.last_payment(i)
                if lp:
                    rows.append((i, (lp - i.date).days))
        self.dtp_rows = rows
        w = sum(self.want(i) for i, _ in rows)
        self.days_to_pay = sum(d * self.want(i) for i, d in rows) / w if w else 0
        self.days_to_pay_median = statistics.median(d for _, d in rows) if rows else 0
        q = defaultdict(list)
        for i, d in rows:
            q[f"{i.date.year}-Q{(i.date.month - 1) // 3 + 1}"].append((i, d))
        self.dtp_by_quarter = {k: {"days": sum(d * self.want(i) for i, d in v) / sum(self.want(i) for i, _ in v), "count": len(v)} for k, v in sorted(q.items())}
        cust_dtp = defaultdict(list)
        for i, d in rows:
            cust_dtp[i.customer_id].append(d)
        self.slow_customers = sorted([{"id": c, "name": self.registry.display(c), "days": statistics.mean(v), "count": len(v)} for c, v in cust_dtp.items() if len(v) >= 4 and statistics.mean(v) > 60],
                                     key=lambda x: -x["days"])
        # overdue ageing at period end
        self.aging = []
        for name, lo, hi in BUCKETS:
            items = [i for i in used if lo <= self._overdue_days(i) <= hi]
            self.aging.append({"key": name, "label": name, "count": len(items), "amount": sum(self.want(i) - self.paid(i) for i in items)})
        not_due = [i for i in used if i.no not in self.circular_invoices and self.status(i) != "paid" and self._overdue_days(i) <= 0 and self.want(i) - self.paid(i) > TOL]
        self.not_yet_due = {"count": len(not_due), "amount": sum(self.want(i) - self.paid(i) for i in not_due)}
        # cash
        cust_dep = [t for t in self.txns if t.category == "customer_receipt"]
        circ_dep = {d.id for d, _, _ in self.circular_pairs}
        genuine = [t for t in cust_dep if t.id not in circ_dep]
        self.cash = {
            "opening": self.statement.opening_balance, "closing": self.closing_balance, "lowest": self.lowest_balance,
            "customer_receipts": sum(t.credit for t in genuine), "avg_monthly_receipts": sum(t.credit for t in genuine) / 12,
            "other_deposits": sum(t.credit for t in self.txns if t.category in NON_SALES),
            "circular": sum(d.credit for d, _, _ in self.circular_pairs),
        }

    # ------------------------------------------------------------------ resolve flags (analyst)
    def resolve(self, flag_id: str, note: str, by: str):
        f = self.flag_by_id.get(flag_id)
        if not f:
            raise KeyError(flag_id)
        if not note.strip():
            raise ValueError("A note is required to resolve a flag.")
        f.resolved = {"note": note.strip(), "by": by or "Analyst", "at": dt.datetime.now().isoformat(timespec="seconds")}
        return f
