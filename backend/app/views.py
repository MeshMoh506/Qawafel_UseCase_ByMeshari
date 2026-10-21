"""Shape the analysis into JSON for the screens: the one-page summary and the rows behind every figure."""
import datetime as dt
from collections import defaultdict

from .analysis import BUCKETS, INV_FILE, NON_SALES, STMT_FILE, Analysis
from .matching import TOL

CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def _iso(d):
    return d.isoformat() if d else None


def invoice_row(a: Analysis, inv) -> dict:
    ms = a.matches_by_inv.get(inv.no, [])
    status = a.status(inv)
    lp = a.last_payment(inv)
    return {
        "kind": "invoice", "id": f"row{inv.row}", "no": inv.no, "date": _iso(inv.date), "due": _iso(a.due(inv)), "due_assumed": inv.due is None,
        "customer": a.registry.display(inv.customer_id) if inv.customer_id else inv.customer_name,
        "name_in_file": inv.customer_name, "net": inv.net, "vat": inv.vat, "total": inv.total, "type": inv.kind,
        "status": status, "paid": a.paid(inv), "outstanding": max(0, a.want(inv) - a.paid(inv)) if inv.kind == "Invoice" and status != "not used (duplicate)" else None,
        "days_to_pay": (lp - inv.date).days if lp and status == "paid" else None,
        "days_overdue": a._overdue_days(inv) or None,
        "paid_by": [{"txn": m.txn_id, "amount": m.applied, "how": m.method, "confidence": m.confidence} for m in ms],
        "source": f"{INV_FILE} · row {inv.row}", "notes": inv.notes + ([f"left out: {a.skipped[inv.row]}"] if inv.row in a.skipped else []),
    }


def txn_row(a: Analysis, t) -> dict:
    ms = a.matches_by_txn.get(t.id, [])
    cid, how = a.result.deposit_customer.get(t.id, (None, None))
    if t.category == "customer_receipt":
        state = "matched" if ms else "no invoice found"
    else:
        state = NON_SALES.get(t.category, "")
    return {
        "kind": "transaction", "id": t.id, "date": _iso(t.date), "description": t.description, "debit": t.debit, "credit": t.credit,
        "balance": t.balance_printed, "category": t.category, "state": state,
        "customer": a.registry.display(cid) if cid else None,
        "applied_to": [{"invoice": m.invoice_no, "amount": m.applied, "how": m.method, "confidence": m.confidence, "note": m.note} for m in ms],
        "source": f"{STMT_FILE} · page {t.page}, line {t.line}",
    }


INV_COLS = [("no", "Invoice"), ("date", "Date"), ("customer", "Customer"), ("net", "Net"), ("total", "Total"), ("status", "Status"), ("days_to_pay", "Days to pay"), ("source", "Source")]
TXN_COLS = [("date", "Date"), ("description", "Description"), ("debit", "Out"), ("credit", "In"), ("state", "Match"), ("source", "Source")]


def _table(name, kind, rows, note=None):
    return {"name": name, "kind": kind, "rows": rows, "note": note}


def figure(a: Analysis, key: str) -> dict | None:
    """Rows behind one number on the summary."""
    used = [i for i in a.invoices if i.kind == "Invoice" and i.row not in a.skipped]
    inv = lambda items: [invoice_row(a, i) for i in sorted(items, key=lambda i: (i.date or dt.date.min, i.no))]
    txn = lambda items: [txn_row(a, t) for t in sorted(items, key=lambda t: (t.date, t.page, t.line))]
    kind, _, arg = key.partition(":")
    if key == "revenue":
        return {"title": "Invoiced revenue after corrections", "how": "Every invoice in the file, once. Repeated rows and re-issued copies are left out. Amounts exclude VAT.",
                "tables": [_table("Invoices", "invoice", inv(used)), _table("Credit notes", "invoice", inv([i for i in a.invoices if i.kind == "Credit Note"]))]}
    if kind == "revenue" and arg:
        sel = [i for i in used if i.date and i.date.strftime("%Y-%m") == arg]
        return {"title": f"Invoices issued in {arg}", "how": "Invoices dated in this month. Amounts exclude VAT.", "tables": [_table("Invoices", "invoice", inv(sel))]}
    if key == "receipts" or (kind == "receipts" and arg):
        circ = {d.id for d, _, _ in a.circular_pairs}
        sel = [t for t in a.txns if t.category == "customer_receipt" and t.id not in circ and (not arg or t.date.strftime("%Y-%m") == arg)]
        return {"title": "Customer payments" + (f" in {arg}" if arg else ""), "how": "Deposits that look like a customer paying. Loans, owner money, own-account transfers, supplier refunds and round-trip payments are left out.",
                "tables": [_table("Bank lines", "transaction", txn(sel))]}
    if key == "confirmed":
        sel = [i for i in used if a.status(i) in ("paid", "partly paid") and i.no not in a.circular_invoices]
        return {"title": "Invoices matched to bank deposits", "how": "Invoices where we found the deposit that paid them. Round-trip invoices are left out.", "tables": [_table("Invoices", "invoice", inv(sel))]}
    if key == "collection":
        sel = [i for i in used if i.no not in a.circular_invoices and a.due(i) and a.due(i) <= a.end]
        return {"title": "Invoices due by the end of the period", "how": "Share of the amount due by 30 September that was paid. Missing due dates are taken as 30 days after the invoice date.",
                "tables": [_table("Invoices", "invoice", inv(sel))]}
    if key == "top5" or kind == "customer":
        if key == "top5":
            ids = {c["id"] for c in a.customers[:5]}
            title, how = "Top 5 customers", "Customers are merged by VAT number, so one customer is counted once even if the file spells the name differently."
        else:
            ids, title, how = {arg}, a.registry.display(arg), "All invoices for this customer."
        sel = [i for i in used if i.customer_id in ids and i.no not in a.circular_invoices]
        return {"title": title, "how": how, "tables": [_table("Invoices", "invoice", inv(sel))]}
    if key == "days_to_pay" or (kind == "days_to_pay" and arg):
        sel = [i for i, d in a.dtp_rows if not arg or f"{i.date.year}-Q{(i.date.month - 1) // 3 + 1}" == arg]
        return {"title": "Days to pay" + (f" ({arg})" if arg else ""), "how": "Days from invoice date to the last deposit that paid it, for invoices paid in full. The average is weighted by invoice value.",
                "tables": [_table("Paid invoices", "invoice", inv(sel))]}
    if key == "overdue" or (kind == "overdue" and arg):
        lo, hi = next(((l, h) for n, l, h in BUCKETS if n == arg), (1, 10**6))
        sel = [i for i in used if lo <= a._overdue_days(i) <= hi]
        return {"title": "Unpaid and past due" + (f": {arg}" if arg else ""), "how": "Invoices with no matching payment whose due date has passed at 30 September. Some may have been paid on a statement page we cannot read.",
                "tables": [_table("Invoices", "invoice", inv(sel))]}
    if key == "not_yet_due":
        sel = [i for i in used if i.no not in a.circular_invoices and a.status(i) != "paid" and a._overdue_days(i) <= 0 and a.want(i) - a.paid(i) > TOL]
        return {"title": "Open and not yet due", "how": "Invoices not fully paid whose due date is after 30 September.", "tables": [_table("Invoices", "invoice", inv(sel))]}
    if key == "other_deposits":
        sel = [t for t in a.txns if t.credit and t.category in NON_SALES]
        return {"title": "Deposits that are not sales", "how": "Left out of revenue and customer payments.", "tables": [_table("Bank lines", "transaction", txn(sel))]}
    if key == "unexplained":
        return {"title": "Customer deposits with no invoice", "how": "Deposits that look like customer payments but match no invoice in this package.", "tables": [_table("Bank lines", "transaction", txn(a.result.unmatched))]}
    if key == "review":
        ids = sorted({m.txn_id for m in a.result.matches if m.confidence != "high"}, key=lambda x: a.tx_by_id[x].date)
        return {"title": "Matches to check", "how": "Matches we are not fully sure about. Low means the customer name was not recognised and we matched on amount alone.", "tables": [_table("Bank lines", "transaction", txn([a.tx_by_id[i] for i in ids]))]}
    if kind == "flag":
        f = a.flag_by_id.get(arg)
        if not f:
            return None
        tables = []
        if f.invoice_rows:
            rows = {i.row: i for i in a.invoices}
            tables.append(_table("Invoice rows", "invoice", inv([rows[r] for r in dict.fromkeys(f.invoice_rows) if r in rows])))
        if f.txn_ids:
            tables.append(_table("Bank lines", "transaction", txn([a.tx_by_id[i] for i in dict.fromkeys(f.txn_ids) if i in a.tx_by_id])))
        if f.pages and not f.txn_ids:
            tables.append({"name": "Statement pages", "kind": "pages", "rows": [{"page": p, "source": f"{STMT_FILE} · page {p}"} for p in f.pages], "note": None})
        return {"title": f.title, "how": f.message, "tables": tables, "flag": flag_json(f)}
    return None


def flag_json(f) -> dict:
    return {"id": f.id, "type": f.type, "severity": f.severity, "title": f.title, "message": f.message, "amount": f.amount, "resolved": f.resolved,
            "count": len(set(f.invoice_rows)) + len(set(f.txn_ids)) + (len(f.pages) if not f.txn_ids else 0)}


def summary(a: Analysis) -> dict:
    mon = a.month_receipts
    months = [{"month": m, "invoiced": v["invoiced"], "receipts": v["receipts"]} for m, v in mon.items()]
    blocking = [f for f in a.flags if f.severity == "blocking"]
    open_block = [f for f in blocking if not f.resolved]
    conf_share = a.confirmed_net / a.invoice_revenue_clean if a.invoice_revenue_clean else 0
    return {
        "business": {"name": "Al Noor Trading Est.", "name_ar": "مؤسسة النور التجارية", "sector": "Food and beverage wholesale, Riyadh", "bank": "Al Amanah Bank (fictional)"},
        "period": {"start": a.start.isoformat(), "end": a.end.isoformat()},
        "package": {"blocking_total": len(blocking), "blocking_open": len(open_block), "warnings": sum(1 for f in a.flags if f.severity == "warning"),
                    "ready": not open_block, "files": {"invoices": INV_FILE, "statement": STMT_FILE, "invoice_rows": len(a.invoices), "bank_lines": len(a.txns), "statement_pages": a.statement.page_count}},
        "bridge": a.bridge,
        "kpis": {
            "revenue": next(b["value"] for b in a.bridge if b["key"] == "clean"),
            "confirmed_net": a.confirmed_net, "confirmed_share": conf_share,
            "collection": a.collection,
            "top5_share": a.top5_share,
            "days_to_pay": a.days_to_pay, "days_to_pay_median": a.days_to_pay_median,
            "receipts_total": a.cash["customer_receipts"], "receipts_avg_month": a.cash["avg_monthly_receipts"],
        },
        "months": months,
        "customers": a.customers[:10],
        "days_by_quarter": [{"quarter": k, **v} for k, v in a.dtp_by_quarter.items()],
        "slow_customers": a.slow_customers,
        "aging": a.aging, "not_yet_due": a.not_yet_due,
        "cash": a.cash,
        "flags": [flag_json(f) for f in a.flags],
        "review_count": len({m.txn_id for m in a.result.matches if m.confidence != "high"}),
        "unexplained": {"count": len(a.result.unmatched), "amount": sum(t.credit for t in a.result.unmatched)},
    }
