// Money arrives as whole halalas (1 SAR = 100 halalas). Format only at the edge.
export const sar = (h, digits = 0) =>
  h == null ? '' : (h / 100).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export const sarM = (h) => `SAR ${(h / 100 / 1e6).toFixed(1)}M`
export const sarK = (h) => `SAR ${Math.round(h / 100 / 1000).toLocaleString('en-US')}k`
export const pct = (x, d = 0) => `${(x * 100).toFixed(d)}%`

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export const day = (iso) => {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  return `${d} ${MONTHS[m - 1]} ${y}`
}
export const monthShort = (ym) => MONTHS[Number(ym.slice(5, 7)) - 1]
export const monthLong = (ym) => `${MONTHS[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`
