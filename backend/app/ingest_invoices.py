"""Read the SME's invoice export (Excel) into clean rows, keeping where each row came from.

The file is messy on purpose: dates stored as text, Arabic-Indic digits, amounts with commas stored
as text, empty cells. Nothing is rejected. A value we cannot read is kept as None and noted.
"""
import datetime as dt
import re
from dataclasses import dataclass, field
from openpyxl import load_workbook

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


@dataclass
class Invoice:
    row: int                      # Excel row number (header is row 1)
    no: str
    date: dt.date | None
    due: dt.date | None
    customer_name: str
    vat_no: str | None
    net: int | None
    vat: int | None
    total: int | None
    kind: str                     # "Invoice" or "Credit Note"
    orig_no: str | None
    notes: list[str] = field(default_factory=list)   # what we had to repair while reading
    customer_id: str = ""         # filled in after customers are merged


def parse_date(v):
    """Return (date or None, note or None)."""
    if v is None or v == "":
        return None, None
    if isinstance(v, dt.datetime):
        return v.date(), None
    if isinstance(v, dt.date):
        return v, None
    raw = str(v).strip()
    s = raw.translate(AR_DIGITS)
    arabic = s != raw
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        return dt.date(y, mo, d), "date was written with Arabic-Indic digits" if arabic else "date was text (dd/mm/yyyy)"
    m = re.fullmatch(r"(\d{1,2}) ([A-Za-z]{3}) (\d{4})", s)
    if m and m.group(2).lower() in MONTHS:
        return dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))), "date was text (d Mon yyyy)"
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return dt.date(*map(int, m.groups())), "date was text (yyyy-mm-dd)"
    return None, f"date not readable: {v!r}"


def parse_money(v):
    """Return (halalas or None, note or None). Accepts numbers and text like '46,654.28'."""
    if v is None or v == "":
        return None, None
    if isinstance(v, (int, float)):
        return int(round(float(v) * 100)), None
    s = str(v).strip().translate(AR_DIGITS).replace(",", "").replace("٫", ".")
    try:
        return int(round(float(s) * 100)), "amount was text"
    except ValueError:
        return None, f"amount not readable: {v!r}"


def read_invoices(path: str) -> list[Invoice]:
    ws = load_workbook(path, data_only=True).active
    header = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    ix = {h: i for i, h in enumerate(header)}
    out = []
    for r_no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(row):
            continue
        get = lambda name: row[ix[name]] if name in ix else None
        notes = []
        date, n1 = parse_date(get("Invoice Date"))
        due, n2 = parse_date(get("Due Date"))
        net, n3 = parse_money(get("Net Amount"))
        vat, n4 = parse_money(get("VAT Amount"))
        tot, n5 = parse_money(get("Total Amount"))
        notes += [n for n in (n1, n2, n3, n4, n5) if n]
        vat_no = str(get("Customer VAT No")).strip() if get("Customer VAT No") not in (None, "") else None
        kind = str(get("Type") or "Invoice").strip()
        orig = str(get("Original Invoice No")).strip() if get("Original Invoice No") not in (None, "") else None
        out.append(Invoice(row=r_no, no=str(get("Invoice No") or "").strip(), date=date, due=due,
                           customer_name=str(get("Customer Name") or "").strip(), vat_no=vat_no,
                           net=net, vat=vat, total=tot, kind=kind, orig_no=orig, notes=notes))
    return out
