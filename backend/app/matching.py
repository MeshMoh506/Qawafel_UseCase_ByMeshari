"""Match bank deposits to invoices.

Steps run from the most certain evidence to the least. Each match records how it was made and how
sure we are, so the analyst only has to look at the unsure ones.

  1. reference     the bank text names the invoice number(s) and the amounts add up        -> high
  2. amount        the customer is known and one open invoice has the same amount           -> high / medium
  3. sum           the customer is known and 2 to 4 open invoices add up to the deposit     -> medium
  4. split         two deposits from the same customer add up to one invoice                -> medium
  5. overpayment   the deposit is a little more than one open invoice (a guess)             -> low
  6. amount_only   the customer name is not recognised; one open invoice has the same amount -> low
Anything left is an unexplained deposit.
"""
import itertools
from dataclasses import dataclass, field

from .names import CustomerRegistry, invoice_refs, name_from_description

TOL = 500                  # SAR 5.00: bank fees and rounding
OVERPAY_MAX = 100_000      # SAR 1,000
SPLIT_DAYS = 21


@dataclass
class Match:
    txn_id: str
    invoice_no: str
    applied: int
    method: str
    confidence: str
    note: str = ""


@dataclass
class OpenInvoice:
    inv: object
    want: int                      # what the customer should pay (total less any linked credit note)
    alt: int | None                # the full total, if a credit note changes `want`
    paid: int = 0

    @property
    def open(self) -> bool:
        return self.paid < self.want - TOL

    def fits(self, amount: int) -> bool:
        return abs(amount - self.want) <= TOL or (self.alt is not None and abs(amount - self.alt) <= TOL)


@dataclass
class Result:
    matches: list[Match] = field(default_factory=list)
    unmatched: list = field(default_factory=list)          # deposits (Txn) nobody explains
    deposit_customer: dict = field(default_factory=dict)   # txn id -> (customer id, how)
    skipped_invoices: dict = field(default_factory=dict)   # invoice row -> reason (duplicates left out of matching)


def match_all(invoices, txns, registry: CustomerRegistry) -> Result:
    res = Result()
    # ---- which invoices take part. Repeated rows and re-issued copies are left out and flagged elsewhere.
    seen_no, seen_sig, pool = set(), {}, []
    credit_by_orig: dict[str, int] = {}
    for inv in sorted(invoices, key=lambda i: i.row):
        if inv.kind == "Credit Note" and inv.orig_no and inv.total:
            credit_by_orig[inv.orig_no] = credit_by_orig.get(inv.orig_no, 0) + inv.total
    for inv in sorted(invoices, key=lambda i: (i.date or 0, i.no)):
        if inv.kind != "Invoice" or inv.total is None or inv.date is None:
            continue
        if inv.no in seen_no:
            res.skipped_invoices[inv.row] = "repeated row"
            continue
        sig = (inv.customer_id, inv.date, inv.net)
        if sig in seen_sig:
            res.skipped_invoices[inv.row] = "same customer, date and amount as " + seen_sig[sig]
            continue
        seen_no.add(inv.no); seen_sig[sig] = inv.no
        cn = credit_by_orig.get(inv.no, 0)
        pool.append(OpenInvoice(inv, inv.total + cn, inv.total if cn else None))
    by_no = {o.inv.no: o for o in pool}
    by_cust: dict[str, list[OpenInvoice]] = {}
    for o in pool:
        by_cust.setdefault(o.inv.customer_id, []).append(o)

    deps = [t for t in txns if t.category == "customer_receipt" and t.credit > 0]
    deps.sort(key=lambda t: (t.date, t.page, t.line))
    for t in deps:
        res.deposit_customer[t.id] = registry.resolve(name_from_description(t.description))
    cust_of = lambda t: res.deposit_customer[t.id][0]
    left = {t.id: t for t in deps}

    def apply(t, pairs, method, conf, note=""):
        for o, amt in pairs:
            o.paid += amt
            res.matches.append(Match(t.id, o.inv.no, amt, method, conf, note))
        left.pop(t.id, None)

    def candidates(cid, t):
        return [o for o in by_cust.get(cid, []) if o.open and o.inv.date <= t.date]

    # 1. reference
    for t in list(left.values()):
        refs = [by_no[r] for r in invoice_refs(t.description) if r in by_no and by_no[r].open]
        if refs and abs(sum(o.want for o in refs) - t.credit) <= TOL * len(refs):
            apply(t, [(o, o.want) for o in refs], "reference", "high", "invoice number(s) written in the bank text")
        elif len(refs) == 1 and t.credit > refs[0].want + TOL and t.credit - refs[0].want <= OVERPAY_MAX:
            apply(t, [(refs[0], refs[0].want)], "reference", "medium", f"deposit is SAR {(t.credit - refs[0].want) / 100:,.2f} more than the invoice")
    # 2. customer + same amount
    for t in list(left.values()):
        cid = cust_of(t)
        if not cid:
            continue
        c = [o for o in candidates(cid, t) if o.fits(t.credit)]
        if c:
            c.sort(key=lambda o: (abs(t.credit - o.want), o.inv.date))
            note = "" if abs(t.credit - c[0].want) <= 1 else f"differs from the invoice by SAR {(t.credit - c[0].want) / 100:+,.2f}"
            apply(t, [(c[0], t.credit)], "amount", "high" if len(c) == 1 else "medium", note)
    # 3. customer + 2..4 invoices that add up
    for t in list(left.values()):
        cid = cust_of(t)
        if not cid:
            continue
        cand = sorted(candidates(cid, t), key=lambda o: o.inv.date)[:30]
        found = []
        for n in (2, 3, 4):
            for combo in itertools.combinations(cand, n):
                if abs(sum(o.want for o in combo) - t.credit) <= TOL:
                    found.append(combo)
            if found:
                break
        if found:
            apply(t, [(o, o.want) for o in found[0]], "sum", "high" if len(found) == 1 else "medium",
                  f"{len(found[0])} invoices add up to the deposit" + ("" if len(found) == 1 else f" ({len(found)} possible sets, oldest chosen)"))
    # 4. two deposits from one customer that add up to one invoice (split payment)
    for cid in {cust_of(t) for t in left.values() if cust_of(t)}:
        mine = [t for t in left.values() if cust_of(t) == cid]
        for o in sorted(by_cust.get(cid, []), key=lambda o: o.inv.date):
            if not o.open or o.paid:
                continue
            for d1, d2 in itertools.combinations(sorted(mine, key=lambda t: t.date), 2):
                if d1.id in left and d2.id in left and d1.date >= o.inv.date and (d2.date - d1.date).days <= SPLIT_DAYS \
                        and abs(d1.credit + d2.credit - o.want) <= TOL and d1.credit >= 0.25 * o.want and d2.credit >= 0.25 * o.want:
                    apply(d1, [(o, d1.credit)], "split", "medium", "first part of a payment made in two deposits")
                    apply(d2, [(o, d2.credit)], "split", "medium", "second part of a payment made in two deposits")
                    break
    # 5. customer + deposit a little above one invoice (overpayment)
    for t in list(left.values()):
        cid = cust_of(t)
        if not cid:
            continue
        c = [o for o in candidates(cid, t) if TOL < t.credit - o.want <= OVERPAY_MAX]
        if c:
            c.sort(key=lambda o: o.inv.date)
            apply(t, [(c[0], c[0].want)], "overpayment", "low",
                  f"deposit is SAR {(t.credit - c[0].want) / 100:,.2f} more than the invoice")
    # 6. customer not recognised: same amount as exactly one open invoice
    for t in list(left.values()):
        if cust_of(t):
            continue
        c = [o for o in pool if o.open and o.inv.date <= t.date and o.fits(t.credit)]
        if len(c) == 1:
            apply(t, [(c[0], t.credit)], "amount_only", "low", "customer name not recognised; matched on amount alone")
    res.unmatched = sorted(left.values(), key=lambda t: (t.date, t.page, t.line))
    return res
