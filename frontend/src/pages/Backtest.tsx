import { useEffect, useState } from 'react'
import { api, type SavedUniverse, type Screen, type Universe } from '../api'
import { SymbolPicker } from '../components/SymbolPicker'

export type StrategyInfo = { id: string; file: string; name: string; description: string; params: Record<string, any>; schedule: any; error: string | null }

const COSTS = {
  slippage_bps: ['Slippage (bps per side)', 10], stt_pct: ['STT %', 0.1], stamp_buy_pct: ['Stamp duty on buys %', 0.015],
  exchange_pct: ['Exchange charge %', 0.00297], brokerage_pct: ['Brokerage %', 0], brokerage_max: ['Brokerage cap per order ₹', 20],
  dp_per_sell: ['DP charge per sell ₹', 15.93],
} as const

// Size bands follow SEBI's market-cap classes (large 1-100, mid 101-250, small 251+).
const SIZE_BANDS: [string, number, number][] = [
  ['Top 50', 1, 50], ['Large 1–100', 1, 100], ['Mid 101–250', 101, 250],
  ['Small 251–750', 251, 750], ['Micro 751–1500', 751, 1500],
]
const RANK_BY: [string, string][] = [
  ['adv_63d', 'Average traded value, 3 months'], ['mcap', 'Market cap (from mid-2022 only)'],
]

const PRESETS: [string, string][] = [['Since 2008', '2008-01-01'], ['10 years', 'y10'], ['5 years', 'y5'], ['3 years', 'y3'], ['1 year', 'y1']]

function presetStart(p: string, end: string) {
  if (!p.startsWith('y')) return p
  const d = end ? new Date(end) : new Date()
  d.setFullYear(d.getFullYear() - Number(p.slice(1)))
  return d.toISOString().slice(0, 10)
}

export function Backtest({ go }: { go: (h: string) => void }) {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [sid, setSid] = useState('')
  const [params, setParams] = useState<Record<string, any>>({})
  const [uKind, setUKind] = useState<'all' | 'manual' | 'saved' | 'screen'>('all')
  const [symbols, setSymbols] = useState<string[]>([])
  const [savedU, setSavedU] = useState<SavedUniverse[]>([])
  const [screens, setScreens] = useState<Screen[]>([])
  const [savedId, setSavedId] = useState('')
  const [screenId, setScreenId] = useState('')
  const [sme, setSme] = useState(false)
  const [start, setStart] = useState('2015-01-01')
  const [end, setEnd] = useState('')
  const [cash, setCash] = useState(10000000)
  const [bench, setBench] = useState('NIFTY50')
  const [benches, setBenches] = useState<string[]>([])
  const [fill, setFill] = useState<'open' | 'close'>('open')
  const [maxVol, setMaxVol] = useState(10)
  const [costs, setCosts] = useState<Record<string, number>>(Object.fromEntries(Object.entries(COSTS).map(([k, v]) => [k, v[1]])))
  const [status, setStatus] = useState<any>(null)
  const [err, setErr] = useState('')
  const [uName, setUName] = useState('')
  const [sliceOn, setSliceOn] = useState(false)
  const [rankBy, setRankBy] = useState('adv_63d')
  const [customBy, setCustomBy] = useState('')
  const [rankFrom, setRankFrom] = useState(1)
  const [rankTo, setRankTo] = useState(50)
  const [refresh, setRefresh] = useState(21)

  useEffect(() => {
    api<StrategyInfo[]>('/strategies').then((s) => { setStrategies(s); const first = s.find((x) => !x.error); if (first) { setSid(first.id); setParams(first.params) } })
    api<SavedUniverse[]>('/universes').then(setSavedU).catch(() => {})
    api<Screen[]>('/screens').then(setScreens).catch(() => {})
    api<string[]>('/benchmarks').then(setBenches).catch(() => {})
  }, [])
  const strat = strategies.find((s) => s.id === sid)

  const baseUniverse = (): Universe => {
    if (uKind === 'manual') return { type: 'manual', symbols }
    if (uKind === 'saved') return savedU.find((u) => u.id === savedId)?.universe ?? { type: 'all' }
    if (uKind === 'screen') return { type: 'screen', screen_id: screenId }
    return { type: 'all', include_sme: sme }
  }
  const universe = (): Universe => {
    const u = baseUniverse()
    if (!sliceOn) return u
    const by = rankBy === 'custom' ? customBy.trim() : rankBy
    return { ...u, rank: { by, from: rankFrom, to: rankTo, refresh } }
  }

  const run = async () => {
    setErr('')
    if (uKind === 'manual' && !symbols.length) { setErr('Pick at least one stock, or choose another universe.'); return }
    if (sliceOn && rankBy === 'custom' && !customBy.trim()) { setErr('Enter a formula to rank stocks by, or pick a preset.'); return }
    if (sliceOn && !(rankFrom >= 1 && rankTo >= rankFrom)) { setErr('Size slice: "to" rank must be at least the "from" rank.'); return }
    try {
      const { id } = await api<{ id: string }>('/backtests', { body: {
        strategy_id: sid, params,
        config: { start, end: end || null, initial_cash: cash, universe: universe(), benchmark: bench, fill, max_volume_pct: maxVol, costs },
      } })
      const poll = async () => {
        const s = await api<any>(`/backtests/${id}`)
        setStatus(s)
        if (s.status === 'running') setTimeout(poll, 700)
        else if (s.status === 'done') go(`#/results/${id}`)
      }
      poll()
    } catch (e: any) { setErr(e.message) }
  }

  const saveManual = async () => {
    const name = uName.trim() || `${symbols.length} stocks`
    await api('/universes', { body: { name, universe: { type: 'manual', symbols } } })
    setSavedU(await api('/universes')); setUName('')
  }

  return (
    <div>
      <h1>New backtest</h1>
      <p className="lede">Each scheduled session the strategy sees data up to that day's close; its orders fill at the next session's open (or close), with Indian delivery costs, slippage and a cap on share of daily volume.</p>
      <div className="grid2">
        <section className="panel stack">
          <h2>Strategy</h2>
          <label className="field">Strategy
            <select value={sid} onChange={(e) => { setSid(e.target.value); setParams(strategies.find((s) => s.id === e.target.value)?.params ?? {}) }}>
              {strategies.map((s) => <option key={s.id} value={s.id} disabled={!!s.error}>{s.name}{s.error ? ' (fails to load)' : ''}</option>)}
            </select>
          </label>
          {strat && <p className="small muted" style={{ margin: 0 }}>{strat.description} <br />Runs: {String(strat.schedule)} · <code>{strat.file}</code></p>}
          {strat && Object.keys(strat.params).length > 0 && (
            <div className="grid3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
              {Object.entries(strat.params).map(([k, def]) => (
                <label className="field" key={k}>{k.replace(/_/g, ' ')}
                  {typeof def === 'boolean'
                    ? <input type="checkbox" checked={!!params[k]} onChange={(e) => setParams((p) => ({ ...p, [k]: e.target.checked }))} />
                    : <input type={typeof def === 'number' ? 'number' : 'text'} value={params[k] ?? ''} step="any"
                        onChange={(e) => setParams((p) => ({ ...p, [k]: typeof def === 'number' ? Number(e.target.value) : e.target.value }))} />}
                </label>
              ))}
            </div>
          )}

          <h2 style={{ marginTop: 8 }}>Universe</h2>
          <div className="seg" role="tablist">
            {([['all', 'All listed'], ['screen', 'Saved screen'], ['saved', 'Saved universe'], ['manual', 'Pick stocks']] as const).map(([k, l]) => (
              <button key={k} className={uKind === k ? 'on' : ''} onClick={() => setUKind(k)}>{l}</button>
            ))}
          </div>
          {uKind === 'all' && <>
            <p className="small muted" style={{ margin: 0 }}>Every stock trading on NSE on each date — including companies that later delisted, so results aren't flattered by survivorship.</p>
            <label className="check"><input type="checkbox" checked={sme} onChange={(e) => setSme(e.target.checked)} /> Include SME board</label>
          </>}
          {uKind === 'screen' && (
            <label className="field">Screen (re-evaluated on every decision date)
              <select value={screenId} onChange={(e) => setScreenId(e.target.value)}>
                <option value="">Choose…</option>{screens.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              {!screens.length && <span className="muted">Save a screen on the Screener page first.</span>}
            </label>
          )}
          {uKind === 'saved' && (
            <label className="field">Universe
              <select value={savedId} onChange={(e) => setSavedId(e.target.value)}>
                <option value="">Choose…</option>{savedU.map((u) => <option key={u.id} value={u.id}>{u.name} ({u.universe.type === 'manual' ? `${u.universe.symbols.length} stocks` : 'screen'})</option>)}
              </select>
            </label>
          )}
          {uKind === 'manual' && <>
            <SymbolPicker value={symbols} onChange={setSymbols} />
            {symbols.length > 0 && <div className="row">
              <input type="text" placeholder="Name this list" value={uName} onChange={(e) => setUName(e.target.value)} />
              <button className="btn small" onClick={saveManual}>Save as universe</button>
            </div>}
          </>}

          <label className="check"><input type="checkbox" checked={sliceOn} onChange={(e) => setSliceOn(e.target.checked)} /> Keep only a size slice of this universe</label>
          {sliceOn && <div className="stack" style={{ gap: 10 }}>
            <div className="row" style={{ gap: 6 }}>
              {SIZE_BANDS.map(([l, a, b]) => (
                <button key={l} className={`btn small ${rankFrom === a && rankTo === b ? 'on' : ''}`} onClick={() => { setRankFrom(a); setRankTo(b) }}>{l}</button>
              ))}
            </div>
            <div className="row">
              <label className="field">Rank by
                <select value={rankBy} onChange={(e) => setRankBy(e.target.value)}>
                  {RANK_BY.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  <option value="custom">Custom formula…</option>
                </select>
              </label>
              <label className="field">From rank<input type="number" min={1} value={rankFrom} onChange={(e) => setRankFrom(Number(e.target.value))} /></label>
              <label className="field">To rank<input type="number" min={1} value={rankTo} onChange={(e) => setRankTo(Number(e.target.value))} /></label>
              <label className="field">Re-rank every (sessions)<input type="number" min={1} value={refresh} onChange={(e) => setRefresh(Number(e.target.value))} /></label>
            </div>
            {rankBy === 'custom' && <label className="field">Formula (highest value = rank 1)
              <input type="text" placeholder="e.g. adv_63d * (close > 20)" value={customBy} onChange={(e) => setCustomBy(e.target.value)} />
            </label>}
            <p className="small muted" style={{ margin: 0 }}>
              Ranks are taken from what was known on each re-rank date, so the slice is the stocks that
              were that size at the time, not today. Traded value works for the whole history; market cap
              needs shares outstanding, which only exist from mid-2022.
            </p>
          </div>}
        </section>

        <section className="panel stack">
          <h2>Period and portfolio</h2>
          <div className="row">
            <label className="field">Start<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
            <label className="field">End<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
          </div>
          <div className="row" style={{ gap: 6 }}>
            {PRESETS.map(([l, p]) => <button key={l} className="btn small" onClick={() => setStart(presetStart(p, end))}>{l}</button>)}
            <span className="small muted">End blank = latest data.</span>
          </div>
          <div className="row">
            <label className="field">Starting capital (₹)<input type="number" value={cash} step={100000} onChange={(e) => setCash(Number(e.target.value))} /></label>
            <label className="field">Benchmark
              <select value={bench} onChange={(e) => setBench(e.target.value)}>{benches.map((b) => <option key={b}>{b}</option>)}</select>
            </label>
          </div>
          <div className="row">
            <label className="field">Orders fill at next session's
              <div className="seg">
                <button className={fill === 'open' ? 'on' : ''} onClick={() => setFill('open')}>Open</button>
                <button className={fill === 'close' ? 'on' : ''} onClick={() => setFill('close')}>Close</button>
              </div>
            </label>
            <label className="field">Max share of day's volume (%)<input type="number" value={maxVol} onChange={(e) => setMaxVol(Number(e.target.value))} /></label>
          </div>
          <details>
            <summary>Transaction costs</summary>
            <div className="grid3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 10, marginTop: 10 }}>
              {Object.entries(COSTS).map(([k, [label]]) => (
                <label className="field" key={k}>{label}<input type="number" step="any" value={costs[k]} onChange={(e) => setCosts((c) => ({ ...c, [k]: Number(e.target.value) }))} /></label>
              ))}
            </div>
            <p className="small muted">GST (18%) applies on brokerage and exchange fees. Defaults match a zero-brokerage discount broker.</p>
          </details>
          <div className="row" style={{ marginTop: 'auto' }}>
            <button className="btn primary" onClick={run} disabled={!sid || status?.status === 'running'}>Run backtest</button>
            {status?.status === 'running' && <span className="small muted">Simulating {status.message}…</span>}
          </div>
          {status?.status === 'running' && <div className="progress"><div style={{ width: `${(status.progress ?? 0) * 100}%` }} /></div>}
          {status?.status === 'error' && <div className="errorbox">{status.message}</div>}
          {err && <div className="errorbox">{err}</div>}
        </section>
      </div>
    </div>
  )
}
