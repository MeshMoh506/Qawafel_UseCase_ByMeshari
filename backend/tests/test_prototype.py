"""Run with:  cd backend && pytest -q"""
import pytest
from fastapi.testclient import TestClient

from app.analysis import Analysis
from app.evaluate import evaluate
from app.ingest_invoices import parse_date, parse_money
from app.main import DATA_DIR, app
from app.names import normalize


@pytest.fixture(scope="module")
def a():
    return Analysis(str(DATA_DIR / "invoices_12m.xlsx"), str(DATA_DIR / "bank_statement_12m.pdf"))


def test_messy_values_are_read():
    assert str(parse_date("٠١/١٠/٢٠٢٦")[0]) == "2026-10-01"
    assert str(parse_date("4 Mar 2026")[0]) == "2026-03-04"
    assert parse_money("46,654.28")[0] == 4665428
    assert parse_date("not a date")[0] is None


def test_name_spellings_collapse():
    assert normalize("سوبرستور  الأندلس Co.") == normalize("سوبرستور الاندلس")


def test_customers_merge_on_vat(a):
    assert len(a.registry.by_id) == 29


def test_statement_reads_every_text_page(a):
    assert a.statement.unreadable_pages == [7]
    assert len(a.txns) == 947


def test_flags_catch_the_planted_blocking_problems(a):
    types = {f.type for f in a.flags if f.severity == "blocking"}
    assert types == {"duplicate_invoice_rows", "possible_reissued_invoice", "unreadable_statement_page", "balance_mismatch", "circular_money"}
    assert a.balance_issues[0]["offset"] == 1_850_000


def test_matching_accuracy_against_the_answer_key(a):
    m = evaluate(a, str(DATA_DIR))["matching"]
    assert m["precision"] >= 0.98 and m["recall"] >= 0.94


def test_money_never_floats(a):
    assert all(isinstance(t.credit, int) and isinstance(t.debit, int) for t in a.txns)


def test_api_resolve_needs_a_note():
    with TestClient(app) as c:
        assert c.post("/v1/flags/F01/resolve", json={"note": "  "}).status_code == 409
        assert c.post("/v1/flags/F01/resolve", json={"note": "Owner confirmed a double export."}).status_code == 200
        s = c.get("/v1/package-versions/demo/summary").json()
        assert s["package"]["blocking_open"] == s["package"]["blocking_total"] - 1
        c.post("/v1/flags/F01/reopen")


def test_unknown_figure_is_404():
    with TestClient(app) as c:
        assert c.get("/v1/package-versions/demo/figures/nope").status_code == 404
