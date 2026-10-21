"""Customer names: the same business shows up in several spellings (Arabic or English, "Co.", extra spaces,
ة/ه). We merge customers by VAT number first, and use normalised names to read bank descriptions."""
import difflib
import re
import unicodedata

_TASHKEEL = re.compile(r"[ً-ْـ]")
_PREFIXES = ("TRANSFER FROM", "SARIE IN", "POS SETTLEMENT", "INWARD TRANSFER")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = _TASHKEEL.sub("", s)
    s = re.sub("[أإآ]", "ا", s).replace("ة", "ه").replace("ى", "ي")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s(co|ltd)$", "", s)
    return s


def name_from_description(desc: str) -> str | None:
    """Pull the customer name out of a bank description such as 'SARIE IN - Al Qasr Restaurant - INV-2026-0012'."""
    d = re.sub(r"\s*-\s*INV-\d{4}-\d{0,4}.*$", "", desc.strip())
    for p in _PREFIXES:
        if d.upper().startswith(p):
            rest = d[len(p):].strip(" -")
            return rest or None
    return None


def invoice_refs(desc: str) -> list[str]:
    return re.findall(r"INV-\d{4}-\d{4}", desc)


class CustomerRegistry:
    """Customers merged by VAT number. Rows with no VAT number join a customer by name."""

    def __init__(self, invoices):
        self.by_id: dict[str, dict] = {}
        self._norm_to_id: dict[str, str] = {}
        rows = sorted(invoices, key=lambda i: (i.vat_no is None, i.row))
        for inv in rows:
            if inv.vat_no:
                cid = inv.vat_no
            else:
                cid = self._norm_to_id.get(normalize(inv.customer_name)) or "name:" + normalize(inv.customer_name)
            c = self.by_id.setdefault(cid, {"id": cid, "vat_no": inv.vat_no, "names": {}})
            c["names"][inv.customer_name] = c["names"].get(inv.customer_name, 0) + 1
            self._norm_to_id.setdefault(normalize(inv.customer_name), cid)
            inv.customer_id = cid
        for c in self.by_id.values():
            c["display"] = max(c["names"].items(), key=lambda kv: kv[1])[0]
            c["variants"] = sorted(c["names"])

    def display(self, cid: str) -> str:
        return self.by_id[cid]["display"]

    def resolve(self, text: str | None) -> tuple[str | None, str]:
        """Return (customer_id or None, how). Exact normalised name first, then a close spelling."""
        if not text:
            return None, "none"
        n = normalize(text)
        if n in self._norm_to_id:
            return self._norm_to_id[n], "exact"
        close = difflib.get_close_matches(n, list(self._norm_to_id), n=1, cutoff=0.88)
        if close:
            return self._norm_to_id[close[0]], "close"
        return None, "unknown"
