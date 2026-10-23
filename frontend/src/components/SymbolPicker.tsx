import { useEffect, useState } from 'react'
import { api } from '../api'

type Hit = { symbol: string; name: string; sector: string; listed: boolean }

export function SymbolPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<Hit[]>([])
  const [paste, setPaste] = useState(false)
  useEffect(() => {
    if (!q.trim()) { setHits([]); return }
    const t = setTimeout(() => api<Hit[]>(`/symbols?q=${encodeURIComponent(q)}`).then(setHits).catch(() => {}), 200)
    return () => clearTimeout(t)
  }, [q])
  const add = (s: string) => { if (!value.includes(s)) onChange([...value, s]); setQ('') }
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ position: 'relative' }}>
        <input type="search" placeholder="Add a stock by symbol or name" value={q} style={{ flex: 1 }}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && hits[0]) add(hits[0].symbol) }} />
        <button className="btn ghost small" onClick={() => setPaste((p) => !p)}>Paste a list</button>
        {hits.length > 0 && (
          <div className="suggest" style={{ left: 0, right: 0 }}>
            {hits.map((h) => (
              <div key={h.symbol} onMouseDown={(e) => { e.preventDefault(); add(h.symbol) }}>
                <code>{h.symbol}</code><span>{h.name} · {h.sector}{h.listed ? '' : ' · no longer trading'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      {paste && (
        <textarea rows={3} placeholder="RELIANCE, TCS, INFY …"
          onBlur={(e) => {
            const syms = e.target.value.toUpperCase().split(/[\s,;]+/).filter(Boolean)
            onChange([...new Set([...value, ...syms])]); setPaste(false)
          }} />
      )}
      <div className="row" style={{ gap: 6 }}>
        {value.map((s) => (
          <span className="chip" key={s}>{s}<button aria-label={`Remove ${s}`} onClick={() => onChange(value.filter((x) => x !== s))}>×</button></span>
        ))}
        {value.length === 0 && <span className="muted small">No stocks picked yet.</span>}
        {value.length > 0 && <button className="btn ghost small" onClick={() => onChange([])}>Clear</button>}
      </div>
    </div>
  )
}
