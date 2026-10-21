import { useEffect, useState } from 'react'
import { getSummary } from '../api.js'
import { day, pct, sar, sarM, monthLong } from '../format.js'
import BarChart from '../components/BarChart.jsx'
import FlagList from '../components/FlagList.jsx'

const fig = (key) => `#/figure/${encodeURIComponent(key)}`

function Figure({ to, label, value, note }) {
  return (
    <a className="figure" href={fig(to)}>
      <span className="figlabel">{label}</span>
      <span className="figvalue">{value}</span>
      <span className="fignote">{note}</span>
    </a>
  )
}

export default function Summary() {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  const load = () => getSummary().then(setS).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  if (err) return <p className="err">Could not load the package: {err}</p>
  if (!s) return <p className="muted">Loading…</p>
  const k = s.kpis
  const flagOf = (type) => s.flags.find((f) => f.type === type)
  const blocking = s.package.blocking_open

  return (
    <div className="page">
      <header className="head">
        <p className="eyebrow">Financing package · version {s.version.version_no}</p>
        <h1>{s.business.name} <span dir="rtl" className="ar">{s.business.name_ar}</span></h1>
        <p className="meta">{s.business.sector} · {day(s.period.start)} to {day(s.period.end)} · {s.package.files.invoice_rows} invoice rows, {s.package.files.bank_lines} bank lines on {s.package.files.statement_pages} statement pages</p>
        <div className={`status ${blocking ? 'stop' : 'go'}`}>
          {blocking
            ? <><strong>Not ready to send to the bank.</strong> {blocking} blocking {blocking === 1 ? 'issue is' : 'issues are'} still open (see Issues below).</>
            : <><strong>Ready to send.</strong> All blocking issues have been resolved with a note.</>}
        </div>
      </header>

      <section className="lead">
        <p>
          Over twelve months this business invoiced <strong>{sarM(k.revenue)}</strong> of genuine sales, excluding VAT.
          {' '}<strong>{pct(k.confirmed_share)}</strong> of it is matched to deposits on the bank statement.
          Customers pay in about <strong>{Math.round(k.days_to_pay)} days</strong>, and <strong>{pct(k.top5_share)}</strong> of revenue comes from five customers.
        </p>
        <p className="muted">Click any figure, bar or row to see the invoices and bank lines behind it.</p>
      </section>

      <section className="figures">
        <Figure to="revenue" label="Revenue, 12 months" value={sarM(k.revenue)} note="after corrections, excluding VAT" />
        <Figure to="confirmed" label="Matched to bank deposits" value={pct(k.confirmed_share)} note="of invoiced revenue" />
        <Figure to="collection" label="Collected, invoices due" value={pct(k.collection.rate)} note={`of SAR ${sar(k.collection.due_amount / 1)} due by ${day(s.period.end)}`} />
        <Figure to="days_to_pay" label="Days to pay" value={Math.round(k.days_to_pay)} note={`weighted average · median ${Math.round(k.days_to_pay_median)}`} />
        <Figure to="top5" label="Top 5 customers" value={pct(k.top5_share)} note="of revenue" />
      </section>

      <section>
        <h2>Invoiced and received, by month</h2>
        <BarChart
          months={s.months}
          onInvoiced={(m) => (window.location.hash = fig('revenue:' + m))}
          onReceipts={(m) => (window.location.hash = fig('receipts:' + m))}
        />
        <p className="legend"><span className="key solid" /> Invoiced, excluding VAT <span className="key outline" /> Customer payments received, including VAT</p>
        <p className="muted">
          Payments are what actually reached the bank. {s.months.filter((m) => m.invoiced && m.receipts < 0.15 * m.invoiced * 1.15).map((m) => monthLong(m.month)).join(', ') || 'No month'} stands out
          {flagOf('month_without_customer_payments') && <> (<a href={fig('flag:' + flagOf('month_without_customer_payments').id)}>see the issue</a>)</>}.
        </p>
      </section>

      <section>
        <h2>From invoiced to confirmed</h2>
        <table className="plain bridge">
          <tbody>
            {s.bridge.map((b) => {
              const f = b.flag && flagOf(b.flag)
              return (
                <tr key={b.key} className={b.total ? 'total' : ''}>
                  <td>{f ? <a href={fig('flag:' + f.id)}>{b.label}</a> : b.key === 'confirmed' ? <a href={fig('confirmed')}>{b.label}</a> : b.key === 'credit_notes' ? <a href={fig('revenue')}>{b.label}</a> : b.label}</td>
                  <td className="num">{b.value < 0 ? `(${sar(-b.value)})` : sar(b.value)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="muted">Amounts in SAR, excluding VAT. “Confirmed” counts an invoice in proportion to the amount we found paid.</p>
      </section>

      <div className="two">
        <section>
          <h2>Customers</h2>
          <table className="plain">
            <thead><tr><th>Customer</th><th className="num">Revenue (SAR)</th><th className="num">Share</th></tr></thead>
            <tbody>
              {s.customers.map((c) => (
                <tr key={c.id}>
                  <td dir="auto"><a href={fig('customer:' + c.id)}>{c.name}</a></td>
                  <td className="num">{sar(c.revenue)}</td>
                  <td className="num">{pct(c.share, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">Top 10 of {s.customers.length >= 10 ? 'all' : ''} customers. Spellings are merged by VAT number.</p>
        </section>

        <section>
          <h2>How fast customers pay</h2>
          <table className="plain">
            <thead><tr><th>Invoices issued in</th><th className="num">Paid in full</th><th className="num">Average days</th></tr></thead>
            <tbody>
              {s.days_by_quarter.map((q) => (
                <tr key={q.quarter}>
                  <td><a href={fig('days_to_pay:' + q.quarter)}>{q.quarter.replace('-', ' ')}</a></td>
                  <td className="num">{q.count}</td>
                  <td className="num">{q.days.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {s.slow_customers.length > 0 && (
            <p className="muted">
              {s.slow_customers.length} customers take more than 60 days on average:{' '}
              {s.slow_customers.map((c, i) => <span key={c.id}>{i ? ', ' : ''}<a dir="auto" href={fig('customer:' + c.id)}>{c.name}</a> ({Math.round(c.days)})</span>)}.
            </p>
          )}
        </section>
      </div>

      <section>
        <h2>Unpaid at {day(s.period.end)}</h2>
        <table className="plain narrow">
          <thead><tr><th>Past due by</th><th className="num">Invoices</th><th className="num">Amount (SAR)</th></tr></thead>
          <tbody>
            {s.aging.map((a) => (
              <tr key={a.key}>
                <td><a href={fig('overdue:' + a.key)}>{a.label}</a></td>
                <td className="num">{a.count}</td>
                <td className="num">{sar(a.amount)}</td>
              </tr>
            ))}
            <tr><td><a href={fig('not_yet_due')}>Open, not yet due</a></td><td className="num">{s.not_yet_due.count}</td><td className="num">{sar(s.not_yet_due.amount)}</td></tr>
          </tbody>
        </table>
        <p className="muted">Amounts include VAT. Invoices with no due date are treated as due 30 days after the invoice date. Some “unpaid” invoices may have been paid on a statement page that cannot be read.</p>
      </section>

      <section>
        <h2>Bank statement</h2>
        <table className="plain narrow">
          <tbody>
            <tr><td>Opening balance</td><td className="num">{sar(s.cash.opening)}</td></tr>
            <tr><td>Closing balance</td><td className="num">{sar(s.cash.closing)}</td></tr>
            <tr><td>Lowest balance printed</td><td className="num">{sar(s.cash.lowest)}</td></tr>
            <tr><td><a href={fig('receipts')}>Customer payments received</a></td><td className="num">{sar(s.cash.customer_receipts)}</td></tr>
            <tr><td>Average per month</td><td className="num">{sar(s.cash.avg_monthly_receipts)}</td></tr>
            <tr><td><a href={fig('other_deposits')}>Deposits that are not sales</a> (left out)</td><td className="num">{sar(s.cash.other_deposits)}</td></tr>
            {flagOf('circular_money') && <tr><td><a href={fig('flag:' + flagOf('circular_money').id)}>Payments that go back out</a> (left out)</td><td className="num">{sar(s.cash.circular)}</td></tr>}
            <tr><td><a href={fig('unexplained')}>Customer deposits with no invoice</a></td><td className="num">{sar(s.unexplained.amount)}</td></tr>
          </tbody>
        </table>
        <p className="muted">Amounts in SAR. Balances are as printed. The statement has a page that cannot be read and a page whose balance does not add up (see Issues).</p>
      </section>

      <section>
        <h2>Issues found by Qawafel</h2>
        <FlagList flags={s.flags} onChange={load} />
        {s.review_count > 0 && <p><a href={fig('review')}>{s.review_count} deposits were matched with less than full confidence →</a></p>}
      </section>
    </div>
  )
}
