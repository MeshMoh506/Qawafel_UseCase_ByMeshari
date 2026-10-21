"""Read the bank statement PDF into transactions.

The PDF has a text layer, so we read the words and their positions. A page with no text layer (a bad scan)
is not guessed at: it is reported as unreadable. Arabic in this PDF is stored in visual order with joined
letter forms, so we convert it back to normal text.
"""
import datetime as dt
import re
import unicodedata
from dataclasses import dataclass
import pdfplumber

NUM = re.compile(r"^\d{1,3}(,\d{3})*\.\d{2}$")
MERGED = re.compile(r"^(\d{1,3}(?:,\d{3})*\.\d{2})(\d{1,3}(?:,\d{3})+\.\d{2})$")   # two amounts printed with no gap
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ARABIC_RUN = re.compile(r"[\u0600-\u06FF]+(?:(?: - | )[\u0600-\u06FF]+)*")
_LAM_ALEF = [chr(c) for c in (0xFEF5, 0xFEF6, 0xFEF7, 0xFEF8, 0xFEF9, 0xFEFA, 0xFEFB, 0xFEFC)]


@dataclass
class Txn:
    id: str                 # "p12-r07": page 12, line 7 on that page. This is where to find it in the PDF.
    page: int
    line: int
    date: dt.date
    description: str
    debit: int
    credit: int
    balance_printed: int
    category: str = ""


@dataclass
class Statement:
    opening_balance: int | None
    period: str | None
    txns: list[Txn]
    unreadable_pages: list[int]
    page_count: int


def _money(s: str) -> int:
    return int(round(float(s.replace(",", "")) * 100))


def _fix_arabic(visual: str) -> str:
    """Visual-order, joined-letter Arabic back to logical Arabic."""
    for lig in _LAM_ALEF:                       # a lam-alef ligature is one glyph, but two letters that must swap back
        visual = visual.replace(lig, unicodedata.normalize("NFKC", lig)[::-1])
    s = unicodedata.normalize("NFKC", visual)
    return ARABIC_RUN.sub(lambda m: m.group(0)[::-1], s)


_RULES = [  # description keyword -> category
    ("LOAN DISBURSEMENT", "loan"), ("OWNER CAPITAL", "owner_injection"), ("TRANSFER FROM OWN ACCOUNT", "own_account_transfer"),
    ("SUPPLIER REFUND", "supplier_refund"), ("REFUND FROM SUPPLIER", "supplier_refund"),
    ("SALARY", "salary"), ("RENT PAYMENT", "rent"), ("UTILITY", "utilities"), ("FUEL", "fuel"), ("BANK FEES", "bank_fees"),
    ("OWNER WITHDRAWAL", "owner_withdrawal"), ("SUPPLIER PAYMENT", "supplier_payment"), ("LOAN INSTALLMENT", "loan_repayment"),
    ("VAT PAYMENT", "vat_payment"), ("REFUND TO CUSTOMER", "refund_to_customer"), ("TRANSFER TO", "transfer_out"),
]
_CUSTOMER_PREFIXES = ("TRANSFER FROM", "SARIE IN", "POS SETTLEMENT", "INWARD TRANSFER")


def categorize(desc: str, credit: int) -> str:
    u = desc.upper()
    for key, cat in _RULES:
        if key in u:
            return cat
    return "customer_receipt" if credit and u.startswith(_CUSTOMER_PREFIXES) else ("other_deposit" if credit else "other_payment")


def read_statement(path: str) -> Statement:
    txns, unreadable = [], []
    opening, period = None, None
    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)
        for pno, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False, x_tolerance=1.5, extra_attrs=[])
            if not words:
                unreadable.append(pno)
                continue
            if pno == 1:
                text = page.extract_text() or ""
                m = re.search(r"Opening Balance:\s*([\d,]+\.\d{2})", text)
                opening = _money(m.group(1)) if m else None
                m = re.search(r"Period:\s*(.+?)$", text, re.M)
                period = m.group(1).strip() if m else None
            rows: list[list] = []                                           # words whose tops are within 2pt share a line
            for w in sorted(words, key=lambda w: w["top"]):
                if rows and abs(w["top"] - rows[-1][0]["top"]) < 2:
                    rows[-1].append(w)
                else:
                    rows.append([w])
            line_no = 0
            for row in rows:
                ws = sorted(row, key=lambda w: w["x0"])
                if not (DATE.match(ws[0]["text"]) and ws[0]["x0"] < 60):
                    continue
                line_no += 1
                debit = credit = bal = None
                desc_words = []
                tokens = []                                   # (text, right edge) of every word after the date
                for w in ws[1:]:
                    m = MERGED.match(w["text"]) if w["x0"] > 380 else None
                    if m:                                     # "43,060.741,457,367.05": split using the glyph positions
                        chars = [c for c in page.chars if abs(c["top"] - w["top"]) < 2 and w["x0"] - 0.5 <= c["x0"] <= w["x1"] + 0.5]
                        chars.sort(key=lambda c: c["x0"])
                        n1 = len(m.group(1))
                        tokens.append((m.group(1), chars[n1 - 1]["x1"] if len(chars) >= len(w["text"]) else w["x0"] + 45))
                        tokens.append((m.group(2), w["x1"]))
                    else:
                        tokens.append((w["text"], w["x1"]))
                for text, x1 in tokens:
                    if NUM.match(text) and x1 > 400:
                        if x1 < 470:
                            debit = _money(text)
                        elif x1 < 545:
                            credit = _money(text)
                        else:
                            bal = _money(text)
                    else:
                        desc_words.append(text)
                desc = _fix_arabic(" ".join(desc_words))
                txns.append(Txn(id=f"p{pno}-r{line_no:02d}", page=pno, line=line_no, date=dt.date.fromisoformat(ws[0]["text"]),
                                description=desc, debit=debit or 0, credit=credit or 0, balance_printed=bal or 0,
                                category=categorize(desc, credit or 0)))
    return Statement(opening, period, txns, unreadable, n_pages)
