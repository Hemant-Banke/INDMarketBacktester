const nf = (d: number) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d })

export function num(v: unknown, d = 2): string {
  if (v === null || v === undefined || typeof v !== 'number' || !Number.isFinite(v)) return '–'
  return nf(d).format(v)
}

export function pct(v: unknown, d = 1, signed = false): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '–'
  const s = nf(d).format(v * 100) + '%'
  return signed && v > 0 ? '+' + s : s
}

/** Indian-style rupee amounts: 1.23 Cr, 4.5 L */
export function inr(v: unknown): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '–'
  const a = Math.abs(v)
  if (a >= 1e7) return `₹${nf(2).format(v / 1e7)} Cr`
  if (a >= 1e5) return `₹${nf(2).format(v / 1e5)} L`
  return `₹${nf(0).format(v)}`
}

export function signClass(v: unknown) {
  return typeof v === 'number' && Number.isFinite(v) ? (v > 0 ? 'pos' : v < 0 ? 'neg' : '') : ''
}

/** Smart cell formatting for screener values. */
export function cell(v: unknown, unit = ''): string {
  if (typeof v === 'string') return v
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (typeof v !== 'number' || !Number.isFinite(v)) return '–'
  const a = Math.abs(v)
  const d = a >= 1000 ? 0 : a >= 100 ? 1 : 2
  return nf(d).format(v) + (unit === '%' ? '%' : '')
}
