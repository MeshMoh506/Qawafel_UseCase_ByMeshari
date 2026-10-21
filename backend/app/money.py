"""Money helpers. All amounts are whole halalas (1 SAR = 100 halalas), never floats."""


def sar(h: int) -> str:
    return f"{h / 100:,.2f}"
