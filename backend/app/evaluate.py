"""Check the prototype against the answer key that came with the sample data. Only for the sample data:
a real customer would not have an answer key."""
import csv
import os
import re
from collections import defaultdict

from .analysis import Analysis, NON_SALES


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def evaluate(a: Analysis, data_dir: str) -> dict | None:
    needed = ["bank_transactions_truth.csv", "ground_truth_matches.csv", "answer_key_issues.csv"]
    if not all(os.path.exists(os.path.join(data_dir, n)) for n in needed):
        return None
    truth = _read(os.path.join(data_dir, "bank_transactions_truth.csv"))
    gt_rows = _read(os.path.join(data_dir, "ground_truth_matches.csv"))
    key_rows = _read(os.path.join(data_dir, "answer_key_issues.csv"))
    cents = lambda s: round(float(s) * 100)
    ours = {(t.date.isoformat(), t.debit, t.credit, t.balance_printed): t.id for t in a.txns}
    tid = {r["txn_id"]: ours.get((r["date"], cents(r["debit"]), cents(r["credit"]), cents(r["balance_printed"]))) for r in truth}
    # ---- matches
    gt = {(tid[r["txn_id"]], r["invoice_no"]) for r in gt_rows if tid.get(r["txn_id"])}
    got = {(m.txn_id, m.invoice_no) for m in a.result.matches}
    tp = len(gt & got)
    page7_pairs = sum(1 for r in gt_rows if not tid.get(r["txn_id"]))
    # a re-issued pair is the same sale twice: paying either copy is right
    twins = {}
    for row, why in a.skipped.items():
        m = re.search(r"INV-\d{4}-\d{4}", why)
        if m:
            mine = next(i.no for i in a.invoices if i.row == row)
            twins[mine] = m.group(0); twins[m.group(0)] = mine
    tp_twin = sum(1 for (t, i) in got - gt if (t, twins.get(i)) in gt)
    by_method = defaultdict(lambda: [0, 0])
    for m in a.result.matches:
        by_method[(m.method, m.confidence)][1] += 1
        if (m.txn_id, m.invoice_no) in gt or (m.txn_id, twins.get(m.invoice_no)) in gt:
            by_method[(m.method, m.confidence)][0] += 1
    # ---- planted problems
    key = defaultdict(set)
    for r in key_rows:
        key[r["issue_type"]].add(r["invoice_no_or_txn_id"])
    F = lambda t: next((f for f in a.flags if f.type == t), None)
    rows_of = lambda f: {next(i.no for i in a.invoices if i.row == r) for r in (f.invoice_rows if f else [])}
    checks = []

    def chk(name, planted, found, extra_note=""):
        planted, found = set(planted), set(found)
        checks.append({"name": name, "planted": len(planted), "found": len(planted & found), "extra": len(found - planted), "note": extra_note})
    rep = F("duplicate_invoice_rows"); chk("Invoice rows that appear twice", key["duplicate_same_number"], {a.invoices[r - 2].no for r in (rep.invoice_rows if rep else [])} if rep else [])
    chk("Invoices re-issued under a new number", key["duplicate_reissued"], {i.no for i in a.invoices if str(a.skipped.get(i.row, "")).startswith("same customer")})
    chk("Missing invoice numbers", key["missing_invoice_number"], a._number_gaps())
    chk("Missing due dates", key["missing_due_date"], rows_of(F("missing_due_date")))
    chk("Missing customer VAT numbers", key["missing_customer_vat"], rows_of(F("missing_customer_vat")))
    chk("Wrong VAT or total", key["arithmetic_error"], rows_of(F("vat_or_total_wrong")))
    chk("Credit notes with no original invoice", key["credit_note_unlinked"], rows_of(F("credit_note_unlinked")))
    chk("Unpaid invoices (over 90 days overdue)", key["unpaid_invoice"], rows_of(F("unpaid_over_90_days")), "one planted invoice is only about a month overdue; the extra ones are mostly paid on the unreadable page")
    circ_inv = {i for i in a.circular_invoices}; chk("Round-trip payments (invoices)", key["circular_money"], circ_inv)
    chk("Statement pages that cannot be read", {"7"} if any(r["issue_type"] == "blurry_page" for r in key_rows) else [], {str(p) for g in a.gaps for p in g["pages"]})
    chk("Statement pages with an edited balance", {r["row_or_page"] for r in key_rows if r["issue_type"] == "edited_balance"}, {str(p) for b in a.balance_issues for p in b["pages"]})
    ns_truth = {tid[t["txn_id"]] for t in truth if t["category"] in NON_SALES and tid.get(t["txn_id"])}
    ns_got = {t.id for t in a.txns if t.credit and t.category in NON_SALES}
    chk("Deposits that are not sales", ns_truth, ns_got)
    var = [c for c in a.registry.by_id.values() if len(c["variants"]) > 1]
    planted_variants = {r["description"].split(";")[0] for r in key_rows if r["issue_type"] in ("customer_name_variant", "related_party_name_variants")}
    chk("Customers written in several spellings", range(len(planted_variants)), range(len(var)))
    march = [f for f in a.flags if f.type == "month_without_customer_payments"]
    chk("Month with almost no customer payments", {"2026-03"}, {re.search(r"\d{4}-\d{2}", f.title).group(0) for f in march})
    return {
        "matching": {"pairs_in_truth": len(gt) + page7_pairs, "pairs_on_readable_pages": len(gt), "pairs_found": len(got), "correct": tp, "correct_including_twins": tp + tp_twin,
                     "precision": (tp + tp_twin) / len(got) if got else 0, "recall": (tp + tp_twin) / len(gt) if gt else 0,
                     "not_readable": page7_pairs,
                     "by_method": [{"method": k[0], "confidence": k[1], "found": v[1], "correct": v[0]} for k, v in sorted(by_method.items())]},
        "flags": checks,
    }
