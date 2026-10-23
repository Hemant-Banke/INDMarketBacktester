import { useEffect, useMemo, useState } from 'react'
import { api, getCatalog, type Catalog, type Column, type Screen } from '../api'
import { DataTable, type Col } from '../components/DataTable'
import { FormulaInput } from '../components/FormulaInput'
import { StockDrawer } from '../components/StockDrawer'
import { cell } from '../format'

const DEFAULT_COLUMNS: Column[] = [
  { name: 'Close', formula: 'close' }, { name: 'Mcap (Cr)', formula: 'mcap' }, { name: 'P/E', formula: 'pe' },
  { name: 'ROE %', formula: 'roe' }, { name: '1M %', formula: 'ret_1m' }, { name: '1Y %', formula: 'ret_1y' },
  { name: 'ADV 20D (Cr)', formula: 'adv_20d' },
]

const EXAMPLES: { name: string; screen: Screen }[] = [
  { name: 'Quality at a fair price', screen: { filters: [{ formula: 'roe > 18' }, { formula: 'debt_equity < 0.5' }, { formula: 'pe > 0 and pe < sector_median(pe)' }, { formula: 'adv_20d > 2' }], sort: { by: 'roe', desc: true } } },
  { name: 'Near 52-week highs, strong trend', screen: { filters: [{ formula: 'pct_from_52w_high > -5' }, { formula: 'close > sma(close, 200)' }, { formula: 'adv_20d > 5' }], sort: { by: 'ret_6m', desc: true } } },
  { name: 'Momentum leaders (top 30)', screen: { filters: [{ formula: 'adv_63d > 5 and close > 20' }], sort: { by: 'ret_12m_1m', desc: true }, limit: 30 } },
  { name: 'Fast-growing small caps', screen: { filters: [{ formula: 'mcap < 5000 and mcap > 500' }, { formula: 'q_revenue_yoy > 25' }, { formula: 'q_net_income_yoy > 25' }], sort: { by: 'q_revenue_yoy', desc: true } } },
]

type Result = { date: string; count: number; columns: string[]; rows: Record<string, any>[] }

export function Screener() {
  const [screen, setScreen] = useState<Screen>({ filters: [{ formula: 'mcap > 1000' }, { formula: '' }], columns: DEFAULT_COLUMNS, sort: { by: 'mcap', desc: true }, limit: null })
  const [asOf, setAsOf] = useState('')
  const [live, setLive] = useState(false)
  const [res, setRes] = useState<Result | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState<Screen[]>([])
  const [drawer, setDrawer] = useState<string | null>(null)
  const [cat, setCat] = useState<Catalog | null>(null)
  const [browse, setBrowse] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => { api<Screen[]>('/screens').then(setSaved).catch(() => {}); getCatalog().then(setCat).catch(() => {}) }, [])

  const run = async () => {
    setBusy(true); setErr('')
    try {
      setRes(await api<Result>('/screen', { body: { screen, as_of: asOf || null, live } }))
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  useEffect(() => { run() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const setFilter = (i: number, f: Partial<{ formula: string; enabled: boolean }>) =>
    setScreen((s) => ({ ...s, filters: s.filters.map((x, j) => (j === i ? { ...x, ...f } : x)) }))
  const setColumn = (i: number, c: Partial<Column>) =>
    setScreen((s) => ({ ...s, columns: (s.columns ?? []).map((x, j) => (j === i ? { ...x, ...c } : x)) }))

  const units = useMemo(() => Object.fromEntries((cat?.metrics ?? []).map((m) => [m.name, m.unit])), [cat])
  const cols: Col<any>[] = useMemo(() => {
    if (!res) return []
    const fixed: Col<any>[] = [
      { key: 'symbol', label: 'Symbol', render: (r) => <b>{r.symbol}</b> },
      { key: 'name', label: 'Name', render: (r) => <span title={r.name}>{String(r.name ?? '').slice(0, 28)}</span> },
      { key: 'sector', label: 'Sector' },
    ]
    const formulaOf = Object.fromEntries((screen.columns ?? []).map((c) => [c.name, c.formula]))
    return [...fixed, ...res.columns.filter((c) => !['symbol', 'name', 'sector', 'industry'].includes(c)).map((c) => ({
      key: c, label: c, num: true, render: (r: any) => cell(r[c], units[formulaOf[c]] ?? ''),
    }))]
  }, [res, screen.columns, units])

  const save = async (asUniverse: boolean) => {
    const nm = screen.name?.trim() || `Screen ${new Date().toLocaleDateString()}`
    if (asUniverse) {
      await api('/universes', { body: { name: nm, universe: { type: 'screen', screen: { ...screen, name: nm } } } })
      setMsg(`Saved universe “${nm}”. Pick it on the Backtest page — it is re-screened on every rebalance date.`)
    } else {
      const s = await api<Screen>('/screens', { body: { ...screen, name: nm } })
      setScreen(s); setSaved(await api('/screens'))
      setMsg(`Saved screen “${nm}”.`)
    }
  }

  const grouped = useMemo(() => {
    const g: Record<string, Catalog['metrics']> = {}
    for (const m of cat?.metrics ?? []) if (live || !m.name.startsWith('tt_')) (g[m.category] ??= []).push(m)
    return g
  }, [cat, live])

  return (
    <div>
      <h1>Screener</h1>
      <p className="lede">Filter every NSE-listed stock with formulas. Pick a past date to see the screen exactly as it would have looked then — prices up to that close, and only financial results already published.</p>

      <div className="panel stack">
        <div className="row">
          <label className="field">Load a screen
            <select value="" onChange={(e) => {
              const v = e.target.value
              const ex = EXAMPLES.find((x) => x.name === v)
              const sv = saved.find((x) => x.id === v)
              if (ex) setScreen({ ...ex.screen, columns: screen.columns, name: ex.name })
              if (sv) setScreen({ columns: DEFAULT_COLUMNS, ...sv })
            }}>
              <option value="">Choose…</option>
              <optgroup label="Examples">{EXAMPLES.map((x) => <option key={x.name}>{x.name}</option>)}</optgroup>
              {saved.length > 0 && <optgroup label="Saved">{saved.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</optgroup>}
            </select>
          </label>
          <label className="field">As of
            <input type="date" value={asOf} onChange={(e) => { setAsOf(e.target.value); if (e.target.value) setLive(false) }} />
          </label>
          <label className="check" title="Adds Tickertape's own screener fields (tt_…). They are a snapshot of today, so only usable for the latest date.">
            <input type="checkbox" checked={live} disabled={!!asOf} onChange={(e) => setLive(e.target.checked)} /> Tickertape live fields
          </label>
          <label className="check"><input type="checkbox" checked={!!screen.base?.include_sme}
            onChange={(e) => setScreen((s) => ({ ...s, base: { ...s.base, include_sme: e.target.checked } }))} /> Include SME board</label>
          <span className="spacer" />
          <button className="btn ghost" onClick={() => setBrowse((b) => !b)}>{browse ? 'Hide metrics' : 'Browse metrics'}</button>
        </div>

        <div>
          <h3>Filters <span className="muted small" style={{ fontWeight: 400 }}>— a stock must pass all of them</span></h3>
          <div className="filters">
            {screen.filters.map((f, i) => (
              <div className="filter-row" key={i}>
                <input type="checkbox" aria-label="Use this filter" checked={f.enabled !== false} onChange={(e) => setFilter(i, { enabled: e.target.checked })} />
                <FormulaInput value={f.formula} live={live} disabled={f.enabled === false} placeholder="e.g. roe > 15 and pe < sector_median(pe)"
                  onChange={(v) => setFilter(i, { formula: v })} />
                <button className="btn ghost small" aria-label="Remove filter" onClick={() => setScreen((s) => ({ ...s, filters: s.filters.filter((_, j) => j !== i) }))}>Remove</button>
              </div>
            ))}
          </div>
          <button className="btn small" style={{ marginTop: 8 }} onClick={() => setScreen((s) => ({ ...s, filters: [...s.filters, { formula: '' }] }))}>Add filter</button>
        </div>

        <details>
          <summary>Columns, sorting and limit</summary>
          <div className="stack" style={{ marginTop: 10, gap: 6 }}>
            {(screen.columns ?? []).map((c, i) => (
              <div className="filter-row" key={i} style={{ gridTemplateColumns: '150px 1fr auto' }}>
                <input type="text" value={c.name} aria-label="Column name" onChange={(e) => setColumn(i, { name: e.target.value })} />
                <FormulaInput value={c.formula} live={live} onChange={(v) => setColumn(i, { formula: v })} />
                <button className="btn ghost small" onClick={() => setScreen((s) => ({ ...s, columns: (s.columns ?? []).filter((_, j) => j !== i) }))}>Remove</button>
              </div>
            ))}
            <div className="row">
              <button className="btn small" onClick={() => setScreen((s) => ({ ...s, columns: [...(s.columns ?? []), { name: 'New column', formula: '' }] }))}>Add column</button>
            </div>
            <div className="filter-row" style={{ gridTemplateColumns: '150px 1fr auto auto' }}>
              <span className="small muted">Sort by formula</span>
              <FormulaInput value={screen.sort?.by ?? ''} live={live} onChange={(v) => setScreen((s) => ({ ...s, sort: { by: v, desc: s.sort?.desc ?? true } }))} />
              <div className="seg">
                <button className={screen.sort?.desc !== false ? 'on' : ''} onClick={() => setScreen((s) => ({ ...s, sort: { by: s.sort?.by ?? '', desc: true } }))}>High first</button>
                <button className={screen.sort?.desc === false ? 'on' : ''} onClick={() => setScreen((s) => ({ ...s, sort: { by: s.sort?.by ?? '', desc: false } }))}>Low first</button>
              </div>
              <label className="row small">Keep top
                <input type="number" min={1} style={{ width: 80 }} value={screen.limit ?? ''} placeholder="all"
                  onChange={(e) => setScreen((s) => ({ ...s, limit: e.target.value ? Number(e.target.value) : null }))} />
              </label>
            </div>
          </div>
        </details>

        <div className="row">
          <button className="btn primary" onClick={run} disabled={busy}>{busy ? 'Screening…' : 'Run screen'}</button>
          <input type="text" placeholder="Name this screen" value={screen.name ?? ''} aria-label="Screen name"
            onChange={(e) => setScreen((s) => ({ ...s, name: e.target.value }))} />
          <button className="btn" onClick={() => save(false)}>Save screen</button>
          <button className="btn" onClick={() => save(true)} title="Use this screen as a point-in-time backtest universe">Save as universe</button>
          {msg && <span className="small muted">{msg}</span>}
        </div>
        {err && <div className="errorbox">{err}</div>}
      </div>

      {browse && cat && (
        <div className="panel">
          <h3>Metrics</h3>
          <p className="small muted" style={{ marginTop: -4 }}>Units: ₹ crore for money, % for ratios marked %. Functions take any expression, e.g. <code>sma(close, 50)</code>, <code>lag(pe, 63)</code>, <code>sector_rank(roe)</code>.</p>
          <div className="grid3">
            {Object.entries(grouped).map(([g, ms]) => (
              <div key={g}>
                <h3 className="small" style={{ color: 'var(--ink-2)' }}>{g}</h3>
                {ms.map((m) => <div key={m.name} className="small" style={{ marginBottom: 3 }}><code>{m.name}</code> <span className="muted">{m.description}</span></div>)}
              </div>
            ))}
            <div>
              <h3 className="small" style={{ color: 'var(--ink-2)' }}>Functions</h3>
              {cat.functions.map((f) => <div key={f.signature} className="small" style={{ marginBottom: 3 }}><code>{f.signature}</code> <span className="muted">{f.description}</span></div>)}
            </div>
          </div>
        </div>
      )}

      {res && (
        <div style={{ marginTop: 20 }}>
          <div className="row" style={{ marginBottom: 8 }}>
            <h2 style={{ margin: 0 }}>{res.count.toLocaleString('en-IN')} stocks</h2>
            <span className="muted">as of the close on {res.date}</span>
          </div>
          <DataTable rows={res.rows} cols={cols} tall onRow={(r) => setDrawer(r.symbol)} empty="No stock passes all filters. Loosen one, or disable it with its checkbox." />
        </div>
      )}
      {drawer && <StockDrawer symbol={drawer} onClose={() => setDrawer(null)} />}
    </div>
  )
}
