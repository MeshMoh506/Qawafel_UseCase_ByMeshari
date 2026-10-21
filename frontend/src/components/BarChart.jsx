import { monthShort, sarM } from '../format.js'

// Two bars per month: invoiced (solid) and customer payments received (outline). Click a bar to see its rows.
export default function BarChart({ months, onInvoiced, onReceipts }) {
  const W = 960, H = 280, L = 52, R = 8, T = 12, B = 30
  const max = Math.max(...months.flatMap((m) => [m.invoiced, m.receipts]))
  const top = Math.ceil(max / 100 / 500000) * 500000 * 100 // round up to SAR 0.5M
  const y = (v) => T + (H - T - B) * (1 - v / top)
  const step = (W - L - R) / months.length
  const bw = Math.min(22, step / 2.6)
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Invoiced and received by month">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="grid" />
          <text x={L - 8} y={y(t) + 4} textAnchor="end" className="axis">{(t / 100 / 1e6).toFixed(1)}M</text>
        </g>
      ))}
      {months.map((m, i) => {
        const cx = L + step * i + step / 2
        return (
          <g key={m.month}>
            <rect x={cx - bw - 2} y={y(m.invoiced)} width={bw} height={y(0) - y(m.invoiced)} className="bar solid" onClick={() => onInvoiced(m.month)}>
              <title>{`${m.month}: invoiced ${sarM(m.invoiced)}. Click to see the invoices.`}</title>
            </rect>
            <rect x={cx + 2} y={y(m.receipts)} width={bw} height={Math.max(1, y(0) - y(m.receipts))} className="bar outline" onClick={() => onReceipts(m.month)}>
              <title>{`${m.month}: customer payments ${sarM(m.receipts)}. Click to see the bank lines.`}</title>
            </rect>
            <text x={cx} y={H - 10} textAnchor="middle" className="axis">{monthShort(m.month)}</text>
          </g>
        )
      })}
    </svg>
  )
}
