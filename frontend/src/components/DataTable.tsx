import { useMemo, useState, type ReactNode } from 'react'
import { tip } from '../glossary'

export type Col<T> = {
  key: string
  label: string
  num?: boolean
  render?: (row: T) => ReactNode
  value?: (row: T) => unknown
}

export function DataTable<T extends Record<string, any>>({ rows, cols, onRow, tall = false, limit = 500, empty }: {
  rows: T[]; cols: Col<T>[]; onRow?: (r: T) => void; tall?: boolean; limit?: number; empty?: ReactNode
}) {
  const [sort, setSort] = useState<{ key: string; desc: boolean } | null>(null)
  const [showAll, setShowAll] = useState(false)
  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = cols.find((c) => c.key === sort.key)
    const get = col?.value ?? ((r: T) => r[sort.key])
    return [...rows].sort((a, b) => {
      const x = get(a), y = get(b)
      const xn = x === null || x === undefined || (typeof x === 'number' && !Number.isFinite(x))
      const yn = y === null || y === undefined || (typeof y === 'number' && !Number.isFinite(y))
      if (xn || yn) return xn && yn ? 0 : xn ? 1 : -1
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
      return sort.desc ? -c : c
    })
  }, [rows, cols, sort])
  if (!rows.length) return <div className="tablewrap"><div className="empty">{empty ?? 'Nothing to show.'}</div></div>
  const shown = showAll ? sorted : sorted.slice(0, limit)
  return (
    <>
      <div className={`tablewrap ${tall ? 'tall' : ''}`}>
        <table className="data">
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c.key} className={c.num ? 'num' : ''} tabIndex={0}
                  aria-sort={sort?.key === c.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}
                  onClick={() => setSort((s) => s?.key === c.key ? { key: c.key, desc: !s.desc } : { key: c.key, desc: !!c.num })}
                  onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLElement).click()}>
                  {tip(c.label) ? <span data-tip={tip(c.label)}>{c.label}</span> : c.label}{sort?.key === c.key && <span className="arrow">{sort.desc ? '↓' : '↑'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={i} className={onRow ? 'click' : ''} onClick={onRow ? () => onRow(r) : undefined}>
                {cols.map((c) => <td key={c.key} className={c.num ? 'num' : ''}>{c.render ? c.render(r) : String(r[c.key] ?? '–')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sorted.length > limit && !showAll && (
        <div className="row small muted" style={{ marginTop: 6 }}>
          Showing {limit} of {sorted.length}.
          <button className="btn small" onClick={() => setShowAll(true)}>Show all</button>
        </div>
      )}
    </>
  )
}
