#!/usr/bin/env python3
"""Generate 12 months of sample data for a fictional Saudi wholesaler (Al Noor Trading Est.).

Outputs (in OUT dir):
  invoices_12m.xlsx            the SME's invoice export (with planted problems)
  bank_statement_12m.pdf       the bank statement (with a blurry page and an edited page)
  bank_transactions_truth.csv  machine-readable twin of the statement
  ground_truth_matches.csv     which deposit pays which invoice (the answer for the matcher)
  answer_key_issues.csv        every planted problem, with its location

Deterministic: seed 42. Money is kept in integer halalas until the very end.
usage: python3 generate_data.py [OUTDIR]
"""
import sys, os, csv, random, datetime as dt
from collections import defaultdict

OUT = sys.argv[1] if len(sys.argv) > 1 else '.'
os.makedirs(OUT, exist_ok=True)
R = random.Random(42)
D = dt.date
P_START, P_END = D(2025, 10, 1), D(2026, 9, 30)
OPENING = 85_000_000            # SAR 850,000.00 in halalas
COMPANY = ('Al Noor Trading Est.', 'مؤسسة النور التجارية')
SAR = lambda x: int(round(x * 100))


def biz(d):                       # Saudi working week: Sun-Thu
    while d.weekday() in (4, 5):
        d += dt.timedelta(days=1)
    return d


def months():
    y, m = 2025, 10
    for _ in range(12):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


# ------------------------------------------------------------------ customers
CUST = [  # (arabic, english, weight, terms days, shift days, kind)
    ('مطعم الجوهرة', 'Al Jawhara Restaurant', 7, 30, -8), ('شركة المزرعة للأغذية', 'Al Mazraa Foods Co.', 6.5, 30, -5),
    ('شركة السفير للتموين', 'Al Safeer Catering Co.', 6, 45, -12), ('روضة مارت', 'Al Rawda Mart', 5.5, 30, -6),
    ('مجموعة فنادق بساتين النخيل', 'Basateen Al Nakheel Hotels', 5, 60, -10), ('سوق الرياض المركزي', 'Riyadh Central Market', 3.2, 30, -4),
    ('مطعم القصر', 'Al Qasr Restaurant', 3.0, 30, -3), ('سوبرستور الأندلس', 'Al Andalus Superstore', 2.8, 30, -7),
    ('نجد غورميه', 'Najd Gourmet', 2.6, 30, -2), ('سوبرماركت النور', 'Al Noor Supermarket', 2.5, 30, 38),
    ('بقالة الرياض الحديثة', 'Bakalah Riyadh Al Haditha', 2.4, 30, -5), ('مشويات النخيل', 'Al Nakheel Grill', 2.3, 30, 0),
    ('الثرية للأغذية', 'Al Thurayya Foods', 2.2, 30, -6), ('الرمول الذهبية للتموين', 'Golden Sands Catering', 2.1, 45, -9),
    ('خليج مارت', 'Khaleej Mart', 2.0, 30, 42), ('مطعم الواحة', 'Al Waha Restaurant', 1.9, 30, -4),
    ('فندق الخليج جراند', 'Gulf Grand Hotel', 1.9, 60, -15), ('بقالة الحي', 'Al Hayy Grocery', 1.7, 30, -6),
    ('مخبز الفجر', 'Al Fajr Bakery', 1.6, 30, -3), ('كافتيريا الشروق', 'Al Shorouk Cafeteria', 1.5, 30, 35),
    ('تموين الصفوة', 'Al Safwa Catering', 1.5, 30, -5), ('أسواق الواحة', 'Al Waha Markets', 1.4, 30, -2),
    ('مطعم سدير', 'Sudair Restaurant', 1.3, 30, -8), ('مركز الرياض للتموين', 'Riyadh Catering Center', 1.2, 45, -7),
    ('بوفيه الديرة', 'Al Dira Buffet', 1.1, 30, 32), ('هايبر المروج', 'Hyper Al Murooj', 1.1, 30, -4),
    ('مطعم الخيمة', 'Al Khaima Restaurant', 1.0, 30, -3), ('سوبرماركت الشمال', 'Al Shamal Supermarket', 1.0, 30, -5),
]
RELATED = ('النخبة للتجارة', 'Al Nokhba Trading')
VARIANT_CUSTOMERS = {3, 7, 8, 9, 10, 4}          # index in CUST: names appear in several spellings


def vat_no(i):
    return '3' + ''.join(str(R.randint(0, 9)) for _ in range(13)) + '3'


class Cust:
    pass


customers = []
for i, (ar, en, w, terms, shift) in enumerate(CUST):
    c = Cust(); c.i = i; c.ar, c.en, c.w, c.terms, c.shift = ar, en, w, terms, shift
    c.vat = vat_no(i)
    c.primary = ar if R.random() < 0.55 else en
    other = en if c.primary == ar else ar
    c.variants = [c.primary]
    if i in VARIANT_CUSTOMERS:
        c.variants += [other, c.primary + ' Co.', c.primary.replace(' ', '  ', 1)]
    c.other = other
    customers.append(c)
rel = Cust(); rel.i = 99; rel.ar, rel.en = RELATED; rel.w = 0; rel.terms = 30; rel.shift = 0
rel.vat = vat_no(99); rel.primary = rel.en; rel.other = rel.ar; rel.variants = [rel.en, rel.ar, rel.ar + ' Co.', rel.ar.replace(' ', '  ', 1)]
tot_w = sum(c.w for c in customers)


def pick_customer():
    x = R.random() * tot_w
    for c in customers:
        x -= c.w
        if x <= 0:
            return c
    return customers[-1]


def inv_name(c):
    if len(c.variants) > 1:
        return R.choices(c.variants, weights=[5, 2, 2, 1])[0]
    return c.primary


def bank_name(c):
    if len(c.variants) > 1:
        return R.choice(c.variants)
    return c.primary if R.random() < 0.75 else c.other


# ------------------------------------------------------------------ invoices
SEAS = {(2025, 10): 1.00, (2025, 11): 1.05, (2025, 12): 0.95, (2026, 1): 1.00, (2026, 2): 1.18, (2026, 3): 1.28,
        (2026, 4): 1.00, (2026, 5): 1.00, (2026, 6): 0.95, (2026, 7): 0.80, (2026, 8): 0.85, (2026, 9): 1.05}
BASE_MONTH_NET = SAR(1_480_000)


class Inv:
    pass


invs = []


def new_inv(date, c, net_h, kind='Invoice'):
    v = Inv(); v.date, v.c, v.net = date, c, net_h
    v.vat = int(round(net_h * 0.15)); v.tot = v.net + v.vat
    v.kind = kind; v.no = None; v.orig = None; v.tags = set(); v.pay = None; v.paid = True
    invs.append(v)
    return v


for (y, m) in months():
    target = int(BASE_MONTH_NET * SEAS[(y, m)] * R.uniform(0.96, 1.04))
    days = []
    d = D(y, m, 1)
    while d.month == m:
        if d.weekday() not in (4, 5) and d <= P_END:
            days.append(d)
        d += dt.timedelta(days=1)
    got = 0
    while got < target:
        c = pick_customer()
        amt = R.lognormvariate(9.6, 0.7) * (1 + c.w / 30)
        net = SAR(min(max(amt, 2500), 80000))
        v = new_inv(R.choice(days), c, net)
        got += net

# related-party customer: 5 invoices, paid next business day and sent back
for k in range(5):
    d = biz(D(2025, 10, 12) + dt.timedelta(days=R.randint(0, 300)))
    v = new_inv(d, rel, SAR(R.randint(38000, 72000)))
    v.tags.add('circular')

# re-issued duplicates (second invoice, same customer/date/amount, new number; only one is paid)
cands = [v for v in invs if v.c.i != 99 and v.date <= D(2026, 8, 15) and not v.tags]
for orig in R.sample(cands, 4):
    cp = new_inv(orig.date, orig.c, orig.net)
    cp.tags.add('reissue_copy'); cp.paid = False; cp.reissue_of = orig
    orig.tags.add('reissue_orig')

# ------------------------------------------------------------------ numbering (with 6 skipped numbers)
invs.sort(key=lambda v: (v.date, R.random()))
total_to_number = len(invs)
skip_at = set(R.sample(range(40, total_to_number + 6), 6))
seq = 0; skipped = []
for v in invs:
    seq += 1
    while seq in skip_at:
        skipped.append(seq); seq += 1
    v.no = f'INV-{v.date.year}-{seq:04d}'
    v.seq = seq
skipped_nos = [f'INV-{(D(2025,10,1)+dt.timedelta(days=0)).year}-{s:04d}' for s in skipped]  # label fixed after (year of neighbour)
# year prefix of a skipped number = year of the invoice that follows it
by_seq = {v.seq: v for v in invs}
skipped_nos = []
for s in skipped:
    nxt = min((v for v in invs if v.seq > s), key=lambda v: v.seq)
    skipped_nos.append(f'INV-{nxt.date.year}-{s:04d}')

# ------------------------------------------------------------------ arithmetic errors (4 wrong total, 4 wrong VAT rate)
plain = [v for v in invs if not v.tags]
errs = R.sample(plain, 8)
for v in errs[:4]:
    v.tot += R.randint(100, 1200); v.tags.add('arith_total')
for v, rate in zip(errs[4:], (0.05, 0.05, 0.0, 0.0)):
    v.vat = int(round(v.net * rate)); v.tot = v.net + v.vat; v.tags.add('arith_vat%d' % int(rate * 100))

# ------------------------------------------------------------------ payments plan
unpaid_pool = [v for v in invs if v.date <= D(2026, 6, 30) and not v.tags and v.c.i != 99]
for v in R.sample(unpaid_pool, 9):
    v.paid = False; v.tags.add('unpaid')


def plan_pay(v):
    lag = v.c.terms + v.c.shift + R.gauss(0, 6)
    lag = max(4, int(round(lag)))
    return biz(v.date + dt.timedelta(days=lag))


for v in invs:
    if v.c.i == 99:
        v.pay = biz(v.date + dt.timedelta(days=1))
    elif v.paid:
        v.pay = plan_pay(v)
# Eid / Ramadan month: nearly all customer payments due in March 2026 arrive in the first week of April
few_left = 0
for v in sorted(invs, key=lambda x: x.date):
    if v.pay and D(2026, 3, 1) <= v.pay <= D(2026, 3, 31) and v.c.i != 99:
        if v.tot < SAR(16000) and few_left < 3:
            few_left += 1
            v.tags.add('march_few'); continue
        v.pay = biz(D(2026, 4, 1) + dt.timedelta(days=R.randint(0, 8)))
        v.tags.add('march_shift')

# ------------------------------------------------------------------ special payment behaviours
used = set()


def free(pred, n):
    pool = [v for v in invs if id(v) not in used and v.paid and v.pay and v.c.i != 99 and v.kind == 'Invoice'
            and 'reissue_copy' not in v.tags and 'march_few' not in v.tags and pred(v)]
    chosen = R.sample(pool, n)
    for v in chosen:
        used.add(id(v))
    return chosen


deposits = []     # dict(date, credit, cust, allocs[(inv, applied)], kind, nameinv)


def add_dep(date, credit, c, allocs, kind, show_inv=None):
    deposits.append(dict(date=date, credit=credit, c=c, allocs=allocs, kind=kind, show=show_inv))


cn_rows = []      # credit notes
cn_small = free(lambda v: v.date <= D(2026, 8, 1) and (v.pay - v.date).days >= 12, 8)
for v in cn_small:
    lag = (v.pay - v.date).days
    cn = new_inv(v.date + dt.timedelta(days=R.randint(4, lag - 3)), v.c, -int(v.net * R.uniform(0.06, 0.25)), 'Credit Note')
    cn.orig = v; cn.tags.add('cn_smaller'); cn.paid = False
    cn_rows.append(cn)
cn_refund = free(lambda v: v.pay <= D(2026, 8, 20), 6)
for v in cn_refund:
    cn = new_inv(v.pay + dt.timedelta(days=R.randint(3, 9)), v.c, -int(v.net * R.uniform(0.05, 0.2)), 'Credit Note')
    cn.orig = v; cn.tags.add('cn_refund'); cn.paid = False
    cn_rows.append(cn)
for k in range(3):
    c = pick_customer()
    cn = new_inv(biz(D(2025, 11, 1) + dt.timedelta(days=R.randint(0, 300))), c, -SAR(R.randint(900, 6000)), 'Credit Note')
    cn.tags.add('cn_unlinked'); cn.paid = False
    cn_rows.append(cn)
# credit notes get their own numbering sequence
cn_rows.sort(key=lambda v: v.date)
for n, cn in enumerate(cn_rows, 1):
    cn.no = f'CN-{cn.date.year}-{n:04d}'
    cn.orig_no = cn.orig.no if cn.orig else None

over = free(lambda v: v.pay <= D(2026, 9, 20), 8)
small = free(lambda v: v.pay <= D(2026, 9, 20), 12)
split = free(lambda v: v.pay <= D(2026, 9, 10) and v.tot > SAR(8000), 25)
# multi-invoice deposits: same customer, pay dates within 6 days of each other
by_c = defaultdict(list)
for v in invs:
    if id(v) not in used and v.paid and v.pay and v.c.i != 99 and v.kind == 'Invoice' and 'reissue_copy' not in v.tags and 'march_few' not in v.tags and v.pay <= D(2026, 9, 25):
        by_c[v.c.i].append(v)
groups = []
for ci, lst in by_c.items():
    lst.sort(key=lambda v: v.pay)
    i = 0
    while i < len(lst) - 1:
        g = [lst[i]]
        j = i + 1
        while j < len(lst) and len(g) < 4 and (lst[j].pay - g[0].pay).days <= 6:
            g.append(lst[j]); j += 1
        if len(g) >= 2:
            groups.append(g)
        i = j
R.shuffle(groups)
multi = groups[:20]
for g in multi:
    for v in g:
        used.add(id(v)); v.tags.add('multi')

# --- deposits for every paid invoice
cn_by_orig = {cn.orig: cn for cn in cn_rows if cn.orig and 'cn_smaller' in cn.tags}
done_multi = set()
for g in multi:
    d = max(v.pay for v in g)
    add_dep(d, sum(v.tot for v in g), g[0].c, [(v, v.tot) for v in g], 'multi_invoice_deposit', show_inv=[v.no for v in g[:3]] if R.random() < 0.5 else None)
    done_multi.update(id(v) for v in g)
for v in invs:
    if not v.paid or not v.pay or v.kind != 'Invoice' or id(v) in done_multi or 'reissue_copy' in v.tags:
        continue
    show = [v.no] if R.random() < 0.25 else None
    if v.c.i == 99:
        add_dep(v.pay, v.tot, v.c, [(v, v.tot)], 'circular_in', show)
        back = v.pay + dt.timedelta(days=R.randint(1, 3))
        deposits.append(dict(date=biz(back), credit=-int(v.tot * R.uniform(0.96, 0.995)), c=v.c, allocs=[], kind='circular_out', show=None, inv=v))
    elif v in split:
        f = R.uniform(0.4, 0.6)
        a = int(v.tot * f)
        d2 = biz(v.pay + dt.timedelta(days=R.randint(4, 14)))
        add_dep(v.pay, a, v.c, [(v, a)], 'split_payment', show)
        add_dep(d2, v.tot - a, v.c, [(v, v.tot - a)], 'split_payment', show)
        v.tags.add('split')
    elif v in over:
        ex = SAR(R.randint(120, 950))
        add_dep(v.pay, v.tot + ex, v.c, [(v, v.tot)], 'overpayment', show)
        v.tags.add('over')
    elif v in small:
        diff = R.choice([-3, -2, -1, 1, 2, 3]) * 100
        add_dep(v.pay, v.tot + diff, v.c, [(v, v.tot + diff)], 'small_difference', show)
        v.tags.add('small'); v.diff = diff
    elif v in cn_by_orig:
        cn = cn_by_orig[v]
        pay = v.tot + int(cn.tot * 1.15)           # customer pays original less the credit note (incl. VAT)
        d = max(v.pay, biz(cn.date + dt.timedelta(days=3)))
        add_dep(d, pay, v.c, [(v, pay)], 'credit_note_smaller', show)
        v.paid_credit = (cn, pay)
    else:
        add_dep(v.pay, v.tot, v.c, [(v, v.tot)], 'normal', show)
# the credit-note total includes VAT so that the stated CN total is what the customer deducts
for cn in cn_rows:
    cn.tot = int(cn.net * 1.15); cn.vat = cn.tot - cn.net
for dep in deposits:                                   # recompute smaller payments with the final CN totals
    if dep['kind'] == 'credit_note_smaller':
        v = dep['allocs'][0][0]; cn = cn_by_orig[v]
        dep['credit'] = v.tot + cn.tot; dep['allocs'] = [(v, dep['credit'])]

# keep anything after period end out (late payers simply have not paid yet)
deposits = [d for d in deposits if d['date'] <= P_END]
# a split payment whose second half falls outside the period leaves the first half paid only (fine, stays a partial)

# ------------------------------------------------------------------ pre-period receipts (older invoices, not in the file)
for k in range(46):
    c = pick_customer()
    d = biz(P_START + dt.timedelta(days=R.randint(0, 55)))
    amt = SAR(min(max(R.lognormvariate(10.2, 0.7), 4000), 80000))
    add_dep(d, amt, c, [], 'pre_period_payment')

# ------------------------------------------------------------------ transactions
tx = []     # dict(date, credit, debit, desc, cat, order, meta)


def T(date, credit=0, debit=0, desc='', cat='other', order=5, meta=None):
    tx.append(dict(date=date, credit=credit, debit=debit, desc=desc, cat=cat, order=order, meta=meta or {}))


def ref_text(show):
    return (' - ' + ' / '.join(show)) if show else ''


for dep in deposits:
    c = dep['c']
    if dep['kind'] == 'circular_out':
        T(dep['date'], debit=-dep['credit'], desc=f'TRANSFER TO {c.en if R.random() < .5 else c.ar} - تحويل صادر', cat='related_party_transfer', order=6, meta=dict(kind='circular_out', inv=dep['inv']))
        continue
    nm = bank_name(c)
    style = R.choice(['TRANSFER FROM {}', 'SARIE IN - {}', 'POS SETTLEMENT - {}', 'INWARD TRANSFER - {}'])
    desc = style.format(nm) + ref_text(dep['show'])
    T(dep['date'], credit=dep['credit'], desc=desc, cat='sales_receipt', order=1, meta=dict(kind=dep['kind'], allocs=dep['allocs'], cust=c))

for cn in cn_rows:
    if 'cn_refund' in cn.tags:
        T(biz(cn.date + dt.timedelta(days=R.randint(2, 6))), debit=-cn.tot, desc=f'REFUND TO CUSTOMER - {bank_name(cn.c)} - استرداد', cat='refund_to_customer', order=6, meta=dict(kind='cn_refund', cn=cn))

# non-sales money in
T(D(2025, 11, 5), credit=SAR(600000), desc='LOAN DISBURSEMENT - BANK AL AMANAH - تمويل', cat='loan', order=1, meta=dict(kind='loan'))
for dd, amt in ((D(2026, 1, 11), 150000), (D(2026, 3, 10), 200000), (D(2026, 6, 14), 180000)):
    T(biz(dd), credit=SAR(amt), desc='OWNER CAPITAL INJECTION - تحويل من صاحب المؤسسة', cat='owner_injection', order=1, meta=dict(kind='owner_injection'))
for k in range(10):
    T(biz(P_START + dt.timedelta(days=R.randint(20, 340))), credit=SAR(R.randint(30, 120) * 1000), desc='TRANSFER FROM OWN ACCOUNT - تحويل من حساب المؤسسة الآخر', cat='own_account_transfer', order=1, meta=dict(kind='own_account_transfer'))
for k in range(5):
    T(biz(P_START + dt.timedelta(days=R.randint(30, 330))), credit=SAR(R.randint(4, 25) * 1000), desc=R.choice(['SUPPLIER REFUND - استرداد من مورد', 'REFUND FROM SUPPLIER - مرتجع مورد']), cat='supplier_refund', order=1, meta=dict(kind='supplier_refund'))

# costs
net_by_month = defaultdict(int)
for v in invs:
    if v.kind == 'Invoice':
        net_by_month[(v.date.year, v.date.month)] += v.net
for (y, m) in months():
    base = net_by_month[(y, m)]
    last = (D(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day
    T(biz(D(y, m, 25)), debit=SAR(118000), desc='SALARY TRANSFER - تحويل رواتب الموظفين', cat='salary')
    T(biz(D(y, m, 25)), debit=SAR(45000), desc='RENT PAYMENT - إيجار المستودع', cat='rent')
    T(biz(D(y, m, 10)), debit=SAR(R.randint(13000, 19500)), desc='UTILITY BILL - فاتورة الكهرباء والماء', cat='utilities')
    for k in range(R.randint(2, 3)):
        T(biz(D(y, m, R.randint(3, 27))), debit=SAR(R.randint(5500, 10500)), desc='FUEL EXPENSE - مصاريف الوقود', cat='fuel')
    for k in range(R.randint(1, 3)):
        T(biz(D(y, m, R.randint(2, last - 1))), debit=SAR(R.randint(250, 1400)), desc='BANK FEES - رسوم بنكية', cat='bank_fees')
    T(biz(D(y, m, R.randint(14, 20))), debit=SAR(R.randint(40, 60) * 1000), desc='OWNER WITHDRAWAL - مسحوبات المالك', cat='owner_withdrawal')
    rec_m = sum(t['credit'] for t in tx if t['cat'] == 'sales_receipt' and (t['date'].year, t['date'].month) == (y, m))
    sp_total = int(0.80 * (0.5 * rec_m + 0.5 * base * 1.15 * 0.92) * R.uniform(0.95, 1.05))
    parts = R.randint(4, 5)
    cuts = sorted(R.random() for _ in range(parts - 1))
    pcs = [b - a for a, b in zip([0] + cuts, cuts + [1])]
    for k, f in enumerate(pcs):
        T(biz(D(y, m, min(last, 3 + k * 6 + R.randint(0, 3)))), debit=int(sp_total * f), desc='SUPPLIER PAYMENT - تحويل إلى مورد', cat='supplier_payment')
    if (y, m) >= (2025, 12) and (y, m) <= (2026, 9):
        T(biz(D(y, m, 5)), debit=SAR(52000), desc='LOAN INSTALLMENT - BANK AL AMANAH - قسط', cat='loan_repayment')
q_net = lambda ms: sum(net_by_month[x] for x in ms)
for dd, ms in ((D(2026, 1, 30), [(2025, 10), (2025, 11), (2025, 12)]), (D(2026, 4, 29), [(2026, 1), (2026, 2), (2026, 3)]), (D(2026, 7, 30), [(2026, 4), (2026, 5), (2026, 6)])):
    T(biz(dd), debit=int(q_net(ms) * 0.10), desc='VAT PAYMENT - ZATCA - دفعة ضريبة القيمة المضافة', cat='vat_payment')

# ------------------------------------------------------------------ order, ids, balances
tx = [t for t in tx if P_START <= t['date'] <= P_END]
tx.sort(key=lambda t: (t['date'], t['order'], R.random()))
bal = OPENING
for n, t in enumerate(tx, 1):
    t['id'] = f'T{n:04d}'
    bal += t['credit'] - t['debit']
    t['bal'] = bal
min_bal = min(t['bal'] for t in tx)
print('min balance SAR', min_bal / 100, ' closing', bal / 100, ' txns', len(tx))
mb = {}
for t in tx: mb[(t['date'].year, t['date'].month)] = t['bal']
print('month-end balances:', {f'{k[0]}-{k[1]:02d}': round(v/100/1000) for k, v in mb.items()}, '(SAR thousands)')
assert min_bal > SAR(40000), 'balance too low - tune costs'

# ------------------------------------------------------------------ messy presentation of invoices (xlsx)
rows = []     # dict per excel row
for v in sorted(invs, key=lambda v: (v.date, v.no or '')):
    rows.append(v)
invoice_rows = [v for v in rows]
# customer names per row, due dates
for v in invoice_rows:
    v.cname = inv_name(v.c)
    v.due = (v.date + dt.timedelta(days=v.c.terms)) if v.kind == 'Invoice' else None
dups = R.sample([v for v in invoice_rows if v.kind == 'Invoice' and not v.tags], 6)     # exact repeated rows appended at the end
export = list(invoice_rows) + dups
issues = []


def issue(kind, file, loc, ref, desc):
    issues.append((kind, file, loc, ref, desc))


# choose disjoint rows for formatting issues
fmt_pool = [v for v in invoice_rows if v.kind == 'Invoice' and not (v.tags & {'reissue_copy'})]
R.shuffle(fmt_pool)
take = lambda n: [fmt_pool.pop() for _ in range(n)]
date_text = take(10); date_arabic = take(5); amt_text = take(10); no_due = take(12); no_vat = take(5)
MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
ARI = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')
for v in date_text:
    v.date_cell = v.date.strftime('%d/%m/%Y') if R.random() < .5 else f'{v.date.day} {MON[v.date.month-1]} {v.date.year}'
for v in date_arabic:
    v.date_cell = v.date.strftime('%d/%m/%Y').translate(ARI)
for v in amt_text:
    v.amt_text = True
vat_missing_cn = [v for v in invoice_rows if v.kind == 'Credit Note' and 'cn_unlinked' not in v.tags][:1]
no_vat += vat_missing_cn

HEAD = ['Invoice No', 'Invoice Date', 'Due Date', 'Customer Name', 'Customer VAT No', 'Net Amount', 'VAT Amount', 'Total Amount', 'Type', 'Original Invoice No', 'Notes']
NOTES = ['Per phone order', 'Delivered to branch 2', 'Frozen goods', 'Special price agreed', 'Return of damaged goods']
from openpyxl import Workbook
wb = Workbook(); ws = wb.active; ws.title = 'Invoices'
ws.append(HEAD)
excel_row = {}
for k, v in enumerate(export):
    r = k + 2
    if k < len(invoice_rows):
        excel_row.setdefault(v.no, r)
    sign = 1
    net, vat, tot = v.net / 100, v.vat / 100, v.tot / 100
    if getattr(v, 'amt_text', False):
        net, vat, tot = f'{net:,.2f}', f'{vat:,.2f}', f'{tot:,.2f}'
    ws.append([v.no, getattr(v, 'date_cell', v.date), (None if v in no_due else (v.due if v.due else None)), v.cname,
               (None if v in no_vat else v.c.vat), net, vat, tot, v.kind, (v.orig.no if v.orig else None),
               (R.choice(NOTES) if R.random() < 0.04 else None)])
    for col in (2, 3):
        c = ws.cell(row=r, column=col)
        if not isinstance(c.value, str):
            c.number_format = 'yyyy-mm-dd'
ws.freeze_panes = 'A2'
for col, w in zip('ABCDEFGHIJK', (16, 14, 14, 34, 18, 14, 13, 14, 12, 18, 26)):
    ws.column_dimensions[col].width = w
wb.save(os.path.join(OUT, 'invoices_12m.xlsx'))

# ------------------------------------------------------------------ PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, ImageFilter
FD = '/usr/share/fonts/truetype/dejavu/'
pdfmetrics.registerFont(TTFont('DV', FD + 'DejaVuSans.ttf')); pdfmetrics.registerFont(TTFont('DVB', FD + 'DejaVuSans-Bold.ttf'))
import re
ARABIC = re.compile(r'[؀-ۿ]')


def shape(s):
    out = []
    # shape arabic runs only; keep latin as is
    parts = re.split(r'(\s+- \s*|\s+)', s)
    txt = get_display(arabic_reshaper.reshape(s)) if ARABIC.search(s) else s
    return txt


PAGE_ROWS = 36
BLURRY_PAGE, EDIT_PAGE, EDIT_DELTA = 7, 12, SAR(18500)
pages = [tx[i:i + PAGE_ROWS] for i in range(0, len(tx), PAGE_ROWS)]
NPAGES = len(pages)
fmt = lambda h: f'{h / 100:,.2f}'
W, H = A4
X = dict(date=36, desc=104, debit=372, credit=450, bal=530)


def header(c, pg, first):
    c.setFont('DVB', 13); c.drawString(36, H - 48, 'Al Amanah Bank')
    c.setFont('DV', 8)
    c.drawString(36, H - 64, 'Account Holder: ' + COMPANY[0] + '  /  ' + shape(COMPANY[1]))
    c.drawString(36, H - 76, 'Account Type: Current Account    IBAN: SA03 8000 0000 1234 5678 9000    Period: 01 Oct 2025 to 30 Sep 2026')
    if first:
        c.drawString(36, H - 90, 'Opening Balance: ' + fmt(OPENING) + ' SAR')
    c.drawRightString(W - 36, H - 48, f'Page {pg} of {NPAGES}')
    y = H - 112
    c.setFont('DVB', 8)
    c.drawString(X['date'], y, 'Date'); c.drawString(X['desc'], y, 'Description')
    c.drawRightString(X['debit'] + 62, y, 'Debit'); c.drawRightString(X['credit'] + 62, y, 'Credit'); c.drawRightString(X['bal'] + 30, y, 'Balance')
    c.line(36, y - 4, W - 36, y - 4)
    return y - 18


def clip(c, s, font, size, maxw):
    t = shape(s)
    while pdfmetrics.stringWidth(t, font, size) > maxw and len(s) > 8:
        s = s[:-1]; t = shape(s)
    return t


tx_page = {}
c = canvas.Canvas(os.path.join(OUT, 'bank_statement_12m.pdf'), pagesize=A4)
c.setTitle('Bank statement'); c.setAuthor('Al Amanah Bank')
for pi, rowsp in enumerate(pages, 1):
    printed = []
    for t in rowsp:
        tx_page[t['id']] = pi
        b = t['bal'] + (EDIT_DELTA if (pi == EDIT_PAGE and rowsp.index(t) >= 9) else 0)
        t['bal_printed'] = b
        printed.append(b)
    if pi == BLURRY_PAGE:
        # render this page as a blurry image (a bad scan) with no text layer
        img = Image.new('L', (1190, 1684), 255)
        dr = ImageDraw.Draw(img)
        f1 = ImageFont.truetype(FD + 'DejaVuSans.ttf', 17); y = 90
        dr.text((60, 60), 'Al Amanah Bank   -   Page %d of %d' % (pi, NPAGES), font=f1, fill=20); y = 150
        def rt(x, yy, txt): dr.text((x - dr.textlength(txt, font=f1), yy), txt, font=f1, fill=30)
        for t in rowsp:
            dr.text((60, y), str(t['date']), font=f1, fill=30)
            dr.text((220, y), shape(t['desc'])[:44], font=f1, fill=30)
            if t['debit']: rt(880, y, fmt(t['debit']))
            if t['credit']: rt(1010, y, fmt(t['credit']))
            rt(1140, y, fmt(t['bal']))
            y += 38
        img = img.filter(ImageFilter.GaussianBlur(5)).resize((img.width // 3, img.height // 3)).resize((img.width, img.height))
        img = img.rotate(0.6, fillcolor=255)
        img.save('/tmp/_scan_page.jpg', quality=35)
        c.drawImage(ImageReader('/tmp/_scan_page.jpg'), 0, 0, width=W, height=H)
        c.showPage(); continue
    y = header(c, pi, pi == 1)
    c.setFont('DV', 7.3)
    for t, b in zip(rowsp, printed):
        c.drawString(X['date'], y, str(t['date']))
        c.drawString(X['desc'], y, clip(c, t['desc'], 'DV', 7.3, 262))
        if t['debit']:
            c.drawRightString(X['debit'] + 62, y, fmt(t['debit']))
        if t['credit']:
            c.drawRightString(X['credit'] + 62, y, fmt(t['credit']))
        c.drawRightString(X['bal'] + 30, y, fmt(b))
        y -= 17
    c.setFont('DV', 6.5); c.drawString(36, 30, 'This statement is computer generated. Fictional bank and customers - sample data for a software assessment.')
    c.showPage()
c.save()

# ------------------------------------------------------------------ truth files
with open(os.path.join(OUT, 'bank_transactions_truth.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['txn_id', 'date', 'description', 'debit', 'credit', 'balance', 'balance_printed', 'category', 'pdf_page'])
    for t in tx:
        w.writerow([t['id'], t['date'], t['desc'], f"{t['debit']/100:.2f}", f"{t['credit']/100:.2f}", f"{t['bal']/100:.2f}", f"{t['bal_printed']/100:.2f}", t['cat'], tx_page[t['id']]])
matches = []
for t in tx:
    if t['meta'].get('allocs'):
        for inv, a in t['meta']['allocs']:
            matches.append((t['id'], inv.no, a, t['meta']['kind']))
with open(os.path.join(OUT, 'ground_truth_matches.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['txn_id', 'invoice_no', 'amount_applied', 'match_type'])
    for m_ in matches:
        w.writerow([m_[0], m_[1], f'{m_[2]/100:.2f}', m_[3]])

# ------------------------------------------------------------------ answer key
def rowof(v): return excel_row[v.no]
cust_variants = [c for c in customers if len(c.variants) > 1] + [rel]
for c_ in customers:
    if len(c_.variants) > 1:
        issue('customer_name_variant', 'both', '', '', f'customer={c_.primary}; variants={c_.variants}')
issue('related_party_name_variants', 'both', '', '', f'customer={rel.en}; variants={rel.variants}')
for v in dups:
    issue('duplicate_same_number', 'invoices_12m.xlsx', f'{excel_row[v.no]} and {len(export) - len(dups) + dups.index(v) + 2}', v.no, 'same row appears twice')
for v in invs:
    if 'reissue_copy' in v.tags:
        issue('duplicate_reissued', 'invoices_12m.xlsx', f'{rowof(v)} (copy) / {rowof(v.reissue_of)} (original)', v.no, f'original_invoice_no={v.reissue_of.no}; same customer, date and amount; only the original was paid')
for cn in cn_rows:
    if cn.orig:
        issue('credit_note_linked', 'invoices_12m.xlsx', rowof(cn), cn.no, f'credit_note={cn.no}; original_invoice_no={cn.orig.no}; ' + ('customer paid the original less this credit' if 'cn_smaller' in cn.tags else 'original was paid in full; the credit was refunded by a bank debit'))
    else:
        issue('credit_note_unlinked', 'invoices_12m.xlsx', rowof(cn), cn.no, 'no Original Invoice No')
for v in invs:
    for tg in v.tags:
        if tg == 'arith_total':
            issue('arithmetic_error', 'invoices_12m.xlsx', rowof(v), v.no, 'Total does not equal Net + VAT')
        if tg.startswith('arith_vat'):
            issue('arithmetic_error', 'invoices_12m.xlsx', rowof(v), v.no, 'VAT computed at ' + tg[-1] + '%' if tg.endswith('0') is False else 'VAT computed at 0%')
for v in no_due: issue('missing_due_date', 'invoices_12m.xlsx', rowof(v), v.no, 'Due Date empty')
for v in no_vat: issue('missing_customer_vat', 'invoices_12m.xlsx', rowof(v), v.no, 'Customer VAT No empty')
for v in date_text: issue('date_text_format', 'invoices_12m.xlsx', rowof(v), v.no, 'value=' + v.date_cell)
for v in date_arabic: issue('date_arabic_indic', 'invoices_12m.xlsx', rowof(v), v.no, 'value=' + v.date_cell)
for v in amt_text: issue('amount_text_commas', 'invoices_12m.xlsx', rowof(v), v.no, 'amounts stored as text with thousands commas')
for v in invs:
    if 'unpaid' in v.tags: issue('unpaid_invoice', 'invoices_12m.xlsx', rowof(v), v.no, 'no payment in the whole period; older than 90 days at period end')
for s in skipped_nos: issue('missing_invoice_number', 'invoices_12m.xlsx', '', s, 'number never appears in the export (gap in the sequence)')
for t in tx:
    k = t['meta'].get('kind')
    if k == 'multi_invoice_deposit':
        issue('multi_invoice_deposit', 'bank_statement_12m.pdf', tx_page[t['id']], t['id'], 'one deposit pays ' + ', '.join(i.no for i, _ in t['meta']['allocs']))
    if k == 'overpayment':
        issue('overpayment', 'bank_statement_12m.pdf', tx_page[t['id']], t['id'], 'invoice=' + t['meta']['allocs'][0][0].no + '; deposit exceeds the invoice')
    if k == 'small_difference':
        issue('small_difference_payment', 'bank_statement_12m.pdf', tx_page[t['id']], t['id'], 'invoice=' + t['meta']['allocs'][0][0].no + f"; diff SAR {t['meta']['allocs'][0][0].diff/100:+.0f}")
    if k == 'credit_note_smaller':
        issue('credit_note_smaller_payment', 'bank_statement_12m.pdf', tx_page[t['id']], t['id'], 'invoice=' + t['meta']['allocs'][0][0].no)
    if k in ('loan', 'owner_injection', 'own_account_transfer', 'supplier_refund'):
        issue('non_sales_deposit', 'bank_statement_12m.pdf', tx_page[t['id']], t['id'], 'category=' + t['cat'])
    if k == 'pre_period_payment':
        issue('payment_for_invoice_outside_period', 'bank_statement_12m.pdf', tx_page[t['id']], t['id'], 'deposit for an invoice issued before the 12 months; no invoice in the file')
seen = set()
for t in tx:
    if t['meta'].get('kind') == 'split_payment' and t['meta']['allocs'][0][0].no not in seen:
        seen.add(t['meta']['allocs'][0][0].no)
        ids = [x['id'] for x in tx if x['meta'].get('kind') == 'split_payment' and x['meta']['allocs'][0][0].no == t['meta']['allocs'][0][0].no]
        issue('split_payment', 'bank_statement_12m.pdf', tx_page[t['id']], t['meta']['allocs'][0][0].no, 'txn_ids=' + ','.join(ids))
for t in tx:
    if t['meta'].get('kind') == 'circular_out':
        inv = t['meta']['inv']
        dep = [x for x in tx if x['meta'].get('kind') == 'circular_in' and x['meta']['allocs'][0][0] is inv][0]
        issue('circular_money', 'both', tx_page[dep['id']], inv.no, f"deposit={dep['id']}; sent back={t['id']}")
mar_sales = sum(t['credit'] for t in tx if t['cat'] == 'sales_receipt' and t['date'].month == 3 and t['date'].year == 2026)
issue('month_without_customer_payments', 'bank_statement_12m.pdf', '', '2026-03', f'March 2026 has only SAR {mar_sales/100:,.2f} of customer payments while invoices were issued as usual')
issue('blurry_page', 'bank_statement_12m.pdf', BLURRY_PAGE, '', 'page is a blurry image with no text')
first_edit = [t for t in tx if tx_page[t['id']] == EDIT_PAGE][9]
issue('edited_balance', 'bank_statement_12m.pdf', EDIT_PAGE, first_edit['id'], f'printed balance is SAR {EDIT_DELTA/100:,.2f} higher than the true running balance from this row to the end of the page')
with open(os.path.join(OUT, 'answer_key_issues.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['issue_id', 'issue_type', 'file', 'row_or_page', 'invoice_no_or_txn_id', 'description'])
    cnt = defaultdict(int)
    for kind, file, loc, ref, desc in issues:
        cnt[kind] += 1
        w.writerow([f'{kind}_{cnt[kind]:03d}', kind, file, loc, ref, desc])

# ------------------------------------------------------------------ self checks
print('--- SELF CHECKS')
inv_only = [v for v in invs if v.kind == 'Invoice']
print('invoices', len(inv_only), ' credit notes', len(cn_rows), ' excel rows', len(export))
print('monthly net revenue (SAR, invoices - credit notes):')
mm = defaultdict(int)
for v in invs: mm[(v.date.year, v.date.month)] += v.net
for k in sorted(mm): print('  %d-%02d  %12s' % (k[0], k[1], f'{mm[k]/100:,.0f}'))
ctot = defaultdict(int)
for v in invs: ctot[v.c.i] += v.net
top5 = sum(sorted(ctot.values(), reverse=True)[:5]) / sum(ctot.values())
print('top-5 customer share of net revenue: %.1f%%' % (top5 * 100))
allc = sum(t['credit'] for t in tx if t['cat'] == 'sales_receipt')
print('customer receipts SAR', f'{allc/100:,.0f}', ' invoiced gross', f"{sum(v.tot for v in inv_only)/100:,.0f}")
# matched share + days to pay
paid_amt = defaultdict(int)
for t in tx:
    for inv, a in t['meta'].get('allocs', []): paid_amt[inv.no] += a
lags = []
for t in tx:
    for inv, a in t['meta'].get('allocs', []): lags.append((t['date'] - inv.date).days)
print('avg days to pay %.1f' % (sum(lags) / len(lags)), '  min', min(lags))
ok = True
bal = OPENING
for t in tx:
    bal += t['credit'] - t['debit']; ok &= (bal == t['bal'])
print('balance chain ok:', ok)
dep_over = [t for t in tx if t['meta'].get('allocs') and sum(a for _, a in t['meta']['allocs']) > t['credit']]
print('deposits where applied > deposit:', len(dep_over))
inv_over = [(n, a) for n, a in paid_amt.items() if a > {v.no: v.tot for v in invs}[n] + 500]
print('invoices applied > total:', len(inv_over))
print('payments before invoice date:', sum(1 for l in lags if l < 0))
print('txns outside period:', sum(1 for t in tx if not P_START <= t['date'] <= P_END))
print('March 2026 sales receipts SAR', f'{mar_sales/100:,.2f}')
by_kind = defaultdict(int)
for kind, *_ in issues: by_kind[kind] += 1
print('planted problems:', dict(by_kind))
print('pages', NPAGES, ' blurry page', BLURRY_PAGE, ' edited page', EDIT_PAGE)
