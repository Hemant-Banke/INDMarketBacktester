import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { axisStyle, baseOption, Chart, SERIES_DARK, SERIES_LIGHT, useTheme, type Theme } from '../components/Chart'
import { DataTable } from '../components/DataTable'
import { StockDrawer } from '../components/StockDrawer'
import { inr, num, pct, signClass } from '../format'
import { tip } from '../glossary'

type Pt = [string, number | null]

// ---------------------------------------------------------------- run list

export function RunList({ go }: { go: (h: string) => void }) {
  const [runs, setRuns] = useState<any[] | null>(null)
  const load = () => api<any[]>('/backtests').then(setRuns)
  useEffect(() => { load() }, [])
  if (!runs) return null
  return (
    <div>
      <div className="row"><h1>Results</h1><span className="spacer" /><button className="btn primary" onClick={() => go('#/backtest')}>New backtest</button></div>
      <p className="lede">Every backtest you've run. Open one to see how it did against its benchmark.</p>
      <DataTable rows={runs} onRow={(r) => r.status === 'done' && go(`#/results/${r.id}`)} empty="No backtests yet. Run one from the Backtest page."
        cols={[
          { key: 'created', label: 'Run at', render: (r) => r.created?.replace('T', ' ') },
          { key: 'strategy_name', label: 'Strategy', render: (r) => <b>{r.strategy_name}</b> },
          { key: 'period', label: 'Period', render: (r) => `${r.config?.start} → ${r.config?.end ?? 'latest'}` },
          { key: 'universe', label: 'Universe', render: (r) => describeUniverse(r.config?.universe) },
          { key: 'cagr', label: 'CAGR', num: true, value: (r) => r.headline?.cagr, render: (r) => <span className={signClass(r.headline?.cagr)}>{pct(r.headline?.cagr)}</span> },
          { key: 'bcagr', label: 'Benchmark CAGR', num: true, value: (r) => r.headline?.benchmark_cagr, render: (r) => pct(r.headline?.benchmark_cagr) },
          { key: 'sharpe', label: 'Sharpe', num: true, value: (r) => r.headline?.sharpe, render: (r) => num(r.headline?.sharpe) },
          { key: 'mdd', label: 'Max drawdown', num: true, value: (r) => r.headline?.max_drawdown, render: (r) => pct(r.headline?.max_drawdown) },
          { key: 'status', label: 'Status', render: (r) => r.status === 'error' ? <span className="neg">failed</span> : r.status },
          { key: 'del', label: '', render: (r) => <button className="btn ghost small" onClick={(e) => { e.stopPropagation(); api(`/backtests/${r.id}`, { method: 'DELETE' }).then(load) }}>Delete</button> },
        ]} />
    </div>
  )
}

function describeUniverse(u: any) {
  if (!u) return '–'
  if (u.type === 'manual') return `${u.symbols.length} picked stocks`
  if (u.type === 'screen') return `Screen ${u.screen?.name ?? u.screen_id ?? ''}`
  return u.include_sme ? 'All listed + SME' : 'All listed'
}

// ---------------------------------------------------------------- run detail

const TABS = ['Overview', 'Returns', 'Rolling', 'Market regimes', 'Trades', 'Holdings', 'Log'] as const

export function RunDetail({ id }: { id: string }) {
  const [meta, setMeta] = useState<any>(null)
  const [r, setR] = useState<any>(null)
  const [err, setErr] = useState('')
  const [tab, setTab] = useState<(typeof TABS)[number]>('Overview')
  const [drawer, setDrawer] = useState<string | null>(null)
  useEffect(() => {
    api(`/backtests/${id}`).then(setMeta).catch((e) => setErr(e.message))
    api(`/backtests/${id}/result`).then(setR).catch((e) => setErr(e.message))
  }, [id])
  if (err) return <div className="errorbox">{err}</div>
  if (!meta || !r) return <p className="muted">Loading…</p>
  const s = r.summary
  return (
    <div>
      <a href="#/results" className="small">All results</a>
      <h1 style={{ marginTop: 6 }}>{meta.strategy_name}</h1>
      <p className="lede" style={{ marginBottom: 6 }}>
        {s.portfolio.start} to {s.portfolio.end} · {describeUniverse(meta.config.universe)} · vs {meta.config.benchmark} · {inr(meta.config.initial_cash)} start
      </p>
      <p className="small muted" style={{ margin: 0 }}>
        Params: {Object.entries(meta.params).map(([k, v]) => `${k}=${v}`).join(', ') || 'defaults'} · fills at next {meta.config.fill}
      </p>
      <Headline s={s} />
      <div className="tabs" role="tablist">
        {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>{t}</button>)}
      </div>
      {tab === 'Overview' && <Overview r={r} />}
      {tab === 'Returns' && <Returns r={r} />}
      {tab === 'Rolling' && <Rolling r={r} />}
      {tab === 'Market regimes' && <Regimes r={r} />}
      {tab === 'Trades' && <Trades r={r} onSymbol={setDrawer} />}
      {tab === 'Holdings' && <Holdings r={r} onSymbol={setDrawer} />}
      {tab === 'Log' && <DataTable rows={r.logs} cols={[{ key: 'date', label: 'Date' }, { key: 'msg', label: 'Message' }]} empty="The strategy didn't log anything. Call ctx.log(...) to record notes." />}
      {drawer && <StockDrawer symbol={drawer} onClose={() => setDrawer(null)} />}
    </div>
  )
}

function Headline({ s }: { s: any }) {
  const rows: [string, (x: any) => string, string, string?][] = [
    ['CAGR', pct, 'cagr'], ['Total return', (v) => pct(v, 0), 'total_return'], ['Volatility', pct, 'volatility'],
    ['Sharpe', num, 'sharpe'], ['Max drawdown', pct, 'max_drawdown'],
  ]
  return (
    <div className="tablewrap" style={{ marginTop: 16, maxWidth: 820 }}>
      <table className="data compare">
        <thead><tr><th></th>{rows.map(([l]) => <th key={l} className="num"><Tip label={l} /></th>)}</tr></thead>
        <tbody>
          <tr><td><b>Strategy</b></td>{rows.map(([l, f, k]) => <td key={l} className="num"><b>{f(s.strategy[k])}</b></td>)}</tr>
          <tr><td>Benchmark</td>{rows.map(([l, f, k]) => <td key={l} className="num">{f(s.benchmark[k])}</td>)}</tr>
          <tr><td>Difference</td>{rows.map(([l, f, k]) => {
            const a = s.strategy[k], b = s.benchmark[k]
            const d = typeof a === 'number' && typeof b === 'number' ? a - b : null
            return <td key={l} className={`num ${k === 'volatility' ? '' : signClass(d)}`}>{d === null ? '–' : (d > 0 ? '+' : '') + f(d)}</td>
          })}</tr>
        </tbody>
      </table>
    </div>
  )
}

// ---------------- overview

function lineSeries(name: string, data: Pt[], color: string, width = 2, extra: any = {}) {
  return { name, type: 'line', showSymbol: false, data, lineStyle: { width, color }, itemStyle: { color }, emphasis: { disabled: true }, ...extra }
}

const BULL_FILL = (t: Theme) => (t.dark ? 'rgba(77,190,140,0.10)' : 'rgba(27,150,100,0.08)')
const BEAR_FILL = (t: Theme) => (t.dark ? 'rgba(230,103,103,0.11)' : 'rgba(196,60,59,0.08)')

/** Shaded spans for Bull and Bear trend regimes; Sideways stays unshaded. */
function regimeAreas(r: any, t: Theme) {
  const tl: [string, string | null][] = r.charts.regime_timeline ?? []
  const kind = (lab: string | null) => (lab?.startsWith('Bull') ? 'bull' : lab?.startsWith('Bear') ? 'bear' : null)
  const areas: any[] = []
  let start: string | null = null
  let cur: string | null = null
  tl.forEach(([d, lab], i) => {
    const k = kind(lab)
    if (k !== cur || i === tl.length - 1) {
      if (cur && start) areas.push([{ xAxis: start, itemStyle: { color: cur === 'bull' ? BULL_FILL(t) : BEAR_FILL(t) } }, { xAxis: d }])
      start = k ? d : null
      cur = k
    }
  })
  return areas
}

function Overview({ r }: { r: any }) {
  const t = useTheme()
  const [log, setLog] = useState(true)
  const c = r.charts
  const equity = useMemo(() => ({
    ...baseOption(t),
    tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => inr(v) },
    xAxis: { type: 'time', ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: log ? 'log' : 'value', scale: true, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => inr(v) } },
    dataZoom: [{ type: 'inside' }],
    series: [
      lineSeries('Benchmark', c.benchmark_equity, t.bench, 1.5, {
        markArea: { silent: true, data: regimeAreas(r, t) },
      }),
      lineSeries('Strategy', c.equity, t.accent, 2),
    ],
  }), [c, t, log, r])
  const dd = useMemo(() => ({
    ...baseOption(t),
    tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => pct(v) },
    xAxis: { type: 'time', ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', max: 0, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => pct(v, 0) } },
    dataZoom: [{ type: 'inside' }],
    series: [
      lineSeries('Benchmark', c.benchmark_drawdown, t.bench, 1.5),
      lineSeries('Strategy', c.drawdown, t.accent, 1.5, { areaStyle: { color: t.accent, opacity: 0.15 } }),
    ],
  }), [c, t])
  const expo = useMemo(() => ({
    ...baseOption(t),
    tooltip: { ...baseOption(t).tooltip },
    xAxis: { type: 'time', ...axisStyle(t), splitLine: { show: false } },
    yAxis: [{ type: 'value', ...axisStyle(t), max: 1.05, axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => pct(v, 0) } }],
    series: [lineSeries('Invested share of equity', c.exposure, t.accent, 1.5, { areaStyle: { color: t.accent, opacity: 0.1 }, tooltip: { valueFormatter: (v: any) => pct(v) } })],
  }), [c, t])
  const pos = useMemo(() => ({
    ...baseOption(t),
    xAxis: { type: 'time', ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisStyle(t), minInterval: 1 },
    series: [lineSeries('Open positions', c.positions, t.accent, 1.5, { step: 'end' })],
  }), [c, t])
  const s = r.summary
  return (
    <div className="stack">
      <section className="panel">
        <div className="row"><h2 style={{ margin: 0 }}>Growth of capital</h2><span className="spacer" />
          <div className="legend"><span><i style={{ background: t.accent }} />Strategy</span><span><i style={{ background: t.bench }} />Benchmark</span>
            <span><i style={{ background: 'rgba(27,150,100,0.3)', height: 8 }} />Bull trend</span>
            <span><i style={{ background: 'rgba(196,60,59,0.3)', height: 8 }} />Bear trend</span></div>
          <div className="seg"><button className={log ? 'on' : ''} onClick={() => setLog(true)}>Log</button><button className={!log ? 'on' : ''} onClick={() => setLog(false)}>Linear</button></div>
        </div>
        <Chart option={equity as any} className="chart tall" />
      </section>
      <section className="panel">
        <h2>Drawdown from previous peak</h2>
        <Chart option={dd as any} className="chart short" />
      </section>
      <div className="grid2">
        <section className="panel"><h2>Exposure</h2><Chart option={expo as any} className="chart short" /></section>
        <section className="panel"><h2>Number of holdings</h2><Chart option={pos as any} className="chart short" /></section>
      </div>
      <div className="grid2">
        <section className="panel"><h2>Risk and return</h2><MetricTable s={s} /></section>
        <section className="panel stack">
          <div><h2>Versus benchmark</h2><KV rows={[
            ['Alpha (annual, CAPM)', pct(s.relative.alpha)], ['Beta', num(s.relative.beta)], ['Correlation', num(s.relative.correlation)],
            ['Tracking error', pct(s.relative.tracking_error)], ['Information ratio', num(s.relative.information_ratio)],
            ['Up-market capture', pct(s.relative.up_capture, 0)], ['Down-market capture', pct(s.relative.down_capture, 0)],
            ['Months beating benchmark', pct(s.relative.months_beating_benchmark, 0)],
          ]} /></div>
          <div><h2>Portfolio</h2><KV rows={[
            ['Final equity', inr(s.portfolio.final_equity)], ['Costs paid', `${inr(s.portfolio.total_fees)} (${pct(s.portfolio.fees_pct_of_initial)} of start)`],
            ['Annual turnover', pct(s.portfolio.annual_turnover, 0)], ['Average invested', pct(s.portfolio.avg_exposure, 0)],
            ['Average holdings', num(s.portfolio.avg_positions, 1)], ['Orders filled', num(s.portfolio.orders_filled, 0)],
          ]} /></div>
          <DrawdownTable rows={r.drawdowns} />
        </section>
      </div>
    </div>
  )
}

function KV({ rows }: { rows: [string, string][] }) {
  return <div className="kv">{rows.map(([k, v]) => <div key={k}><span><Tip label={k} /></span><b>{v}</b></div>)}</div>
}

/** A metric label that explains itself on hover or focus, when the glossary has an entry. */
function Tip({ label }: { label: string }) {
  const text = tip(label)
  return text ? <span data-tip={text} tabIndex={0}>{label}</span> : <>{label}</>
}

function MetricTable({ s }: { s: any }) {
  const rows: [string, string, (v: any) => string][] = [
    ['Total return', 'total_return', (v) => pct(v, 0)], ['CAGR', 'cagr', pct], ['Volatility (annual)', 'volatility', pct],
    ['Sharpe (rf 6.5%)', 'sharpe', num], ['Sortino', 'sortino', num], ['Calmar', 'calmar', num],
    ['Max drawdown', 'max_drawdown', pct], ['Longest drawdown (sessions)', 'max_drawdown_sessions', (v) => num(v, 0)],
    ['Best day', 'best_day', pct], ['Worst day', 'worst_day', pct], ['Best month', 'best_month', pct], ['Worst month', 'worst_month', pct],
    ['Positive months', 'positive_months', (v) => pct(v, 0)], ['Daily VaR 95%', 'var_95', (v) => pct(v, 2)],
    ['Daily CVaR 95%', 'cvar_95', (v) => pct(v, 2)], ['Skew', 'skew', num], ['Excess kurtosis', 'kurtosis', num],
  ]
  return (
    <table className="data compare">
      <thead><tr><th></th><th className="num">Strategy</th><th className="num">Benchmark</th></tr></thead>
      <tbody>{rows.map(([l, k, f]) => <tr key={k}><td><Tip label={l} /></td><td className="num">{f(s.strategy[k])}</td><td className="num">{f(s.benchmark[k])}</td></tr>)}</tbody>
    </table>
  )
}

function DrawdownTable({ rows }: { rows: any[] }) {
  return (
    <div>
      <h2>Worst drawdowns</h2>
      <DataTable rows={rows} cols={[
        { key: 'depth', label: 'Depth', num: true, render: (r) => pct(r.depth) },
        { key: 'start', label: 'Peak' }, { key: 'trough', label: 'Trough' },
        { key: 'recovery', label: 'Recovered', render: (r) => r.recovery ?? 'not yet' },
        { key: 'sessions_total', label: 'Sessions', num: true, render: (r) => r.sessions_total ?? '–' },
      ]} />
    </div>
  )
}

// ---------------- returns

function diverging(v: number | null, t: Theme, scale = 0.08) {
  if (v === null || !Number.isFinite(v)) return 'transparent'
  const a = Math.min(Math.abs(v) / scale, 1) * (t.dark ? 0.55 : 0.45)
  return v >= 0 ? `rgba(42,120,214,${a})` : `rgba(208,59,59,${a})`
}

function Returns({ r }: { r: any }) {
  const t = useTheme()
  const [which, setWhich] = useState<'strategy' | 'benchmark' | 'excess'>('strategy')
  const years = [...new Set(r.monthly.map((m: any) => m.year))] as number[]
  const byKey = new Map(r.monthly.map((m: any) => [`${m.year}-${m.month}`, m]))
  const yearly = new Map(r.yearly.map((y: any) => [y.year, y]))
  const val = (m: any) => !m ? null : which === 'excess' ? (m.benchmark == null ? null : m.strategy - m.benchmark) : m[which]
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const yearlyOpt = useMemo(() => ({
    ...baseOption(t), legend: { show: false },
    tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => pct(v) },
    xAxis: { type: 'category', data: r.yearly.map((y: any) => String(y.year)), ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => pct(v, 0) } },
    series: [
      { name: 'Strategy', type: 'bar', data: r.yearly.map((y: any) => y.strategy), itemStyle: { color: t.accent, borderRadius: [4, 4, 0, 0] }, barGap: '8%' },
      { name: 'Benchmark', type: 'bar', data: r.yearly.map((y: any) => y.benchmark), itemStyle: { color: t.bench, borderRadius: [4, 4, 0, 0] } },
    ],
  }), [r, t])
  const hist = useMemo(() => histogram(r.charts.daily_returns, 0.002, 0.06), [r])
  const histOpt = useMemo(() => ({
    ...baseOption(t), tooltip: { ...baseOption(t).tooltip, trigger: 'axis' },
    xAxis: { type: 'category', data: hist.labels, ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisStyle(t), name: 'sessions', nameTextStyle: { color: t.ink3 } },
    series: [{ name: 'Sessions', type: 'bar', data: hist.counts, barCategoryGap: '8%', itemStyle: { color: t.accent, borderRadius: [2, 2, 0, 0] } }],
  }), [hist, t])
  return (
    <div className="stack">
      <section className="panel">
        <div className="row"><h2 style={{ margin: 0 }}>Monthly returns</h2><span className="spacer" />
          <div className="seg">{(['strategy', 'benchmark', 'excess'] as const).map((k) => <button key={k} className={which === k ? 'on' : ''} onClick={() => setWhich(k)}>{k === 'excess' ? 'Strategy minus benchmark' : k[0].toUpperCase() + k.slice(1)}</button>)}</div>
        </div>
        <div className="tablewrap" style={{ marginTop: 12 }}>
          <table className="data">
            <thead><tr><th>Year</th>{months.map((m) => <th key={m} className="num">{m}</th>)}<th className="num">Year</th></tr></thead>
            <tbody>{years.map((y) => {
              const yr: any = yearly.get(y)
              const yv = yr ? (which === 'excess' ? (yr.benchmark == null ? null : yr.strategy - yr.benchmark) : yr[which]) : null
              return (
                <tr key={y}><td>{y}</td>
                  {months.map((_, i) => { const v = val(byKey.get(`${y}-${i + 1}`)); return <td key={i} className="num" style={{ background: diverging(v, t) }}>{v == null ? '' : pct(v)}</td> })}
                  <td className="num" style={{ background: diverging(yv, t, 0.4), fontWeight: 500 }}>{pct(yv)}</td>
                </tr>
              )
            })}</tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <div className="row"><h2 style={{ margin: 0 }}>Calendar-year returns</h2><span className="spacer" />
          <div className="legend"><span><i style={{ background: t.accent, height: 8 }} />Strategy</span><span><i style={{ background: t.bench, height: 8 }} />Benchmark</span></div></div>
        <Chart option={yearlyOpt as any} />
      </section>
      <section className="panel">
        <h2>Distribution of daily returns</h2>
        <Chart option={histOpt as any} className="chart short" />
      </section>
    </div>
  )
}

function histogram(xs: number[], step: number, clip: number) {
  const n = Math.round((2 * clip) / step)
  const counts = new Array(n).fill(0)
  for (const x of xs) {
    const k = Math.min(n - 1, Math.max(0, Math.floor((x + clip) / step)))
    counts[k]++
  }
  const labels = counts.map((_, i) => pct(-clip + i * step, 1))
  return { counts, labels }
}

// ---------------- rolling

function Rolling({ r }: { r: any }) {
  const t = useTheme()
  const c = r.charts
  const mk = (title: string, a: Pt[], b: Pt[] | null, fmt: (v: number) => string, ref?: number) => ({
    title,
    opt: {
      ...baseOption(t), tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => (v == null ? '–' : fmt(v)) },
      xAxis: { type: 'time', ...axisStyle(t), splitLine: { show: false } },
      yAxis: { type: 'value', scale: true, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: fmt } },
      series: [
        ...(b ? [lineSeries('Benchmark', b, t.bench, 1.5)] : []),
        lineSeries('Strategy', a, t.accent, 1.5, ref !== undefined ? { markLine: { silent: true, symbol: 'none', lineStyle: { color: t.ink3, type: 'dashed' }, data: [{ yAxis: ref }], label: { show: false } } } : {}),
      ],
    },
  })
  const charts = [
    mk('Rolling 1-year return', c.rolling_return, c.rolling_return_benchmark, (v) => pct(v, 0), 0),
    mk('Rolling 1-year volatility', c.rolling_vol, c.rolling_vol_benchmark, (v) => pct(v, 0)),
    mk('Rolling 1-year Sharpe', c.rolling_sharpe, null, (v) => num(v, 1), 0),
    mk('Rolling 1-year beta to benchmark', c.rolling_beta, null, (v) => num(v, 2), 1),
    mk('Strategy ÷ benchmark (rising = outperforming)', c.relative, null, (v) => num(v, 2), 1),
  ]
  return (
    <div className="stack">
      <div className="legend"><span><i style={{ background: t.accent }} />Strategy</span><span><i style={{ background: t.bench }} />Benchmark</span></div>
      <div className="grid2">
        {charts.map((ch) => <section className="panel" key={ch.title}><h2>{ch.title}</h2><Chart option={ch.opt as any} className="chart short" /></section>)}
      </div>
    </div>
  )
}

// ---------------- regimes

function Regimes({ r }: { r: any }) {
  const t = useTheme()
  const sections: [string, string, string][] = [
    ['trend', 'Benchmark trend', 'Bull: benchmark above a rising 200-day average. Bear: below a falling one. Sideways: anything else. Each day is labelled with what was known at the previous close, so the label lags: a fall usually starts in Sideways, and the rebound off a bottom stays Bear until the benchmark climbs back above its average.'],
    ['benchmark_drawdown', 'Benchmark distance from its high', 'How far the benchmark was below its all-time high at the previous close.'],
    ['volatility', 'Benchmark volatility', 'One-month realised volatility, compared with the terciles of all volatility seen up to that day.'],
  ]
  if (!r.regimes?.trend) return <div className="note">Regime analysis needs benchmark data for the period.</div>
  return (
    <div className="stack">
      {sections.map(([k, title, desc]) => {
        const rows = r.regimes[k] as any[]
        const opt = {
          ...baseOption(t), tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => pct(v) },
          grid: { left: 8, right: 16, top: 10, bottom: 8, containLabel: true },
          yAxis: { type: 'category', data: rows.map((x) => x.regime), ...axisStyle(t), splitLine: { show: false }, inverse: true },
          xAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => pct(v, 0) } },
          series: [
            { name: 'Strategy (annualised)', type: 'bar', data: rows.map((x) => x.strategy_ann_return), itemStyle: { color: t.accent, borderRadius: 4 }, barGap: '10%' },
            { name: 'Benchmark (annualised)', type: 'bar', data: rows.map((x) => x.benchmark_ann_return), itemStyle: { color: t.bench, borderRadius: 4 } },
          ],
        }
        return (
          <section className="panel" key={k}>
            <h2>{title}</h2>
            <p className="small muted" style={{ marginTop: -4 }}>{desc}</p>
            <div className="stack">
              <Chart option={opt as any} className="chart short" />
              <DataTable rows={rows} cols={[
                { key: 'regime', label: 'Regime' },
                { key: 'share_of_time', label: 'Time', num: true, render: (x) => pct(x.share_of_time, 0) },
                { key: 'strategy_ann_return', label: 'Strategy ann.', num: true, render: (x) => <span className={signClass(x.strategy_ann_return)}>{pct(x.strategy_ann_return)}</span> },
                { key: 'benchmark_ann_return', label: 'Bench ann.', num: true, render: (x) => pct(x.benchmark_ann_return) },
                { key: 'strategy_vol', label: 'Strategy vol', num: true, render: (x) => pct(x.strategy_vol) },
                { key: 'hit_rate_vs_benchmark', label: 'Days ahead', num: true, render: (x) => pct(x.hit_rate_vs_benchmark, 0) },
              ]} />
            </div>
          </section>
        )
      })}
      <section className="panel">
        <h2>Notable market episodes</h2>
        <p className="small muted" style={{ marginTop: -4 }}>Episodes only partly inside the backtest are marked.</p>
        <DataTable rows={r.episodes} empty="No notable episodes fall inside this period." cols={[
          { key: 'episode', label: 'Episode', render: (x) => <>{x.episode}{x.partial && <span className="muted small"> (partial)</span>}</> },
          { key: 'start', label: 'From' }, { key: 'end', label: 'To' },
          { key: 'strategy_return', label: 'Strategy', num: true, render: (x) => <span className={signClass(x.strategy_return)}>{pct(x.strategy_return)}</span> },
          { key: 'benchmark_return', label: 'Benchmark', num: true, render: (x) => pct(x.benchmark_return) },
          { key: 'diff', label: 'Difference', num: true, value: (x) => x.strategy_return - (x.benchmark_return ?? 0), render: (x) => <span className={signClass(x.strategy_return - x.benchmark_return)}>{pct(x.strategy_return - x.benchmark_return, 1, true)}</span> },
          { key: 'strategy_max_dd', label: 'Strategy max DD', num: true, render: (x) => pct(x.strategy_max_dd) },
          { key: 'benchmark_max_dd', label: 'Bench max DD', num: true, render: (x) => pct(x.benchmark_max_dd) },
        ]} />
      </section>
    </div>
  )
}

// ---------------- trades

function Trades({ r, onSymbol }: { r: any; onSymbol: (s: string) => void }) {
  const t = useTheme()
  const ts = r.summary.trades
  const [view, setView] = useState<'round' | 'fills'>('round')
  const hist = useMemo(() => {
    const xs: number[] = r.charts.trade_returns
    const edges = [-100, -50, -30, -20, -10, -5, 0, 5, 10, 20, 30, 50, 100, 200, Infinity]
    const counts = edges.slice(0, -1).map((lo, i) => xs.filter((x) => x >= lo && x < edges[i + 1]).length)
    const labels = edges.slice(0, -1).map((lo, i) => edges[i + 1] === Infinity ? `≥${lo}%` : `${lo} to ${edges[i + 1]}%`)
    return { counts, labels, edges }
  }, [r])
  const opt = {
    ...baseOption(t),
    xAxis: { type: 'category', data: hist.labels, ...axisStyle(t), splitLine: { show: false }, axisLabel: { ...axisStyle(t).axisLabel, rotate: 30 } },
    yAxis: { type: 'value', ...axisStyle(t), minInterval: 1 },
    series: [{ name: 'Round trips', type: 'bar', barCategoryGap: '10%', data: hist.counts.map((c, i) => ({ value: c, itemStyle: { color: hist.edges[i] < 0 ? t.neg : t.pos, borderRadius: [3, 3, 0, 0] } })) }],
  }
  return (
    <div className="stack">
      <div className="grid2">
        <section className="panel">
          <h2>Trade statistics</h2>
          {ts.round_trips ? <KV rows={[
            ['Closed round trips', num(ts.round_trips, 0)], ['Win rate', pct(ts.win_rate, 0)],
            ['Average win', `${num(ts.avg_win_pct, 1)}%`], ['Average loss', `${num(ts.avg_loss_pct, 1)}%`],
            ['Profit factor', num(ts.profit_factor)], ['Median holding', `${num(ts.median_sessions_held, 0)} sessions`],
            ['Best trade', `${num(ts.best_trade_pct, 1)}%`], ['Worst trade', `${num(ts.worst_trade_pct, 1)}%`],
            ...Object.entries(ts.exit_reasons ?? {}).map(([k, v]) => [`Exits: ${k}`, String(v)] as [string, string]),
          ]} /> : <p className="muted">No position has been closed yet.</p>}
        </section>
        <section className="panel"><h2>Round-trip returns</h2><Chart option={opt as any} className="chart short" /></section>
      </div>
      <div className="seg"><button className={view === 'round' ? 'on' : ''} onClick={() => setView('round')}>Round trips</button><button className={view === 'fills' ? 'on' : ''} onClick={() => setView('fills')}>All fills</button></div>
      {view === 'round' ? (
        <DataTable rows={r.round_trips} tall onRow={(x) => onSymbol(x.symbol)} cols={[
          { key: 'symbol', label: 'Symbol', render: (x) => <b>{x.symbol}</b> }, { key: 'entry_date', label: 'Entry' }, { key: 'exit_date', label: 'Exit' },
          { key: 'qty', label: 'Qty', num: true, render: (x) => num(x.qty, 0) },
          { key: 'entry_price', label: 'Entry ₹', num: true, render: (x) => num(x.entry_price) },
          { key: 'exit_price', label: 'Exit ₹', num: true, render: (x) => num(x.exit_price) },
          { key: 'return_pct', label: 'Return', num: true, render: (x) => <span className={signClass(x.return_pct)}>{num(x.return_pct, 1)}%</span> },
          { key: 'pnl', label: 'P&L (after costs)', num: true, render: (x) => <span className={signClass(x.pnl)}>{inr(x.pnl)}</span> },
          { key: 'sessions_held', label: 'Sessions', num: true }, { key: 'exit_reason', label: 'Exit reason' },
        ]} />
      ) : (
        <DataTable rows={r.fills} tall onRow={(x) => onSymbol(x.symbol)} cols={[
          { key: 'date', label: 'Date' }, { key: 'symbol', label: 'Symbol', render: (x) => <b>{x.symbol}</b> },
          { key: 'side', label: 'Side', render: (x) => <span className={x.side === 'buy' ? 'pos' : 'neg'}>{x.side}</span> },
          { key: 'qty', label: 'Qty', num: true, render: (x) => num(x.qty, 0) }, { key: 'price', label: 'Price ₹', num: true, render: (x) => num(x.price) },
          { key: 'value', label: 'Value', num: true, render: (x) => inr(x.value) }, { key: 'fees', label: 'Costs', num: true, render: (x) => inr(x.fees) },
          { key: 'reason', label: 'Reason' },
        ]} />
      )}
    </div>
  )
}

// ---------------- holdings

function Holdings({ r, onSymbol }: { r: any; onSymbol: (s: string) => void }) {
  const t = useTheme()
  const palette = t.dark ? SERIES_DARK : SERIES_LIGHT
  const sectorOpt = useMemo(() => {
    const rows: any[] = r.sector_exposure
    const totals: Record<string, number> = {}
    for (const row of rows) for (const [k, v] of Object.entries(row)) if (k !== 'date' && k !== 'cash') totals[k] = (totals[k] ?? 0) + (v as number)
    const top = Object.entries(totals).sort((a, b) => b[1] - a[1]).map(([k]) => k)
    const keep = top.slice(0, 7)
    const series = [...keep, 'Other', 'Cash'].map((name, i) => ({
      name, type: 'line', stack: 'w', showSymbol: false, areaStyle: { opacity: 0.85 }, lineStyle: { width: 0 },
      color: name === 'Cash' ? t.rule : name === 'Other' ? t.bench : palette[i],
      data: rows.map((row) => [row.date, name === 'Cash' ? row.cash
        : name === 'Other' ? Object.entries(row).filter(([k]) => k !== 'date' && k !== 'cash' && !keep.includes(k)).reduce((a, [, v]) => a + (v as number), 0)
        : row[name] ?? 0]),
    }))
    return {
      ...baseOption(t), legend: { bottom: 0, textStyle: { color: t.ink2 }, icon: 'roundRect', itemWidth: 10, itemHeight: 10 },
      grid: { left: 8, right: 16, top: 16, bottom: 36, containLabel: true },
      tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => pct(v, 0) },
      xAxis: { type: 'time', ...axisStyle(t), splitLine: { show: false } },
      yAxis: { type: 'value', max: 1, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => pct(v, 0) } },
      series,
    }
  }, [r, t, palette])
  const contrib = useMemo(() => {
    const rows = [...r.contributors.top.slice(0, 10), ...r.contributors.bottom.slice(0, 10).reverse()]
      .filter((x, i, a) => a.findIndex((y) => y.symbol === x.symbol) === i).sort((a, b) => b.pnl - a.pnl)
    return {
      ...baseOption(t), tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => inr(v) },
      yAxis: { type: 'category', data: rows.map((x) => x.symbol), inverse: true, ...axisStyle(t), splitLine: { show: false } },
      xAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => inr(v) } },
      series: [{ type: 'bar', name: 'P&L', data: rows.map((x) => ({ value: x.pnl, itemStyle: { color: x.pnl >= 0 ? t.pos : t.neg, borderRadius: 3 } })) }],
    }
  }, [r, t])
  return (
    <div className="stack">
      <section className="panel"><h2>Sector weights at month ends</h2><Chart option={sectorOpt as any} className="chart tall" /></section>
      <div className="grid2">
        <section className="panel"><h2>Biggest contributors and detractors</h2>
          <Chart option={contrib as any} className="chart tall" onClick={(p: any) => p?.name && onSymbol(p.name)} /></section>
        <section className="panel"><h2>Open at the end</h2>
          <DataTable rows={r.open_positions} onRow={(x) => onSymbol(x.symbol)} empty="No open positions at the end." cols={[
            { key: 'symbol', label: 'Symbol', render: (x) => <b>{x.symbol}</b> },
            { key: 'weight', label: 'Weight', num: true, render: (x) => pct(x.weight) },
            { key: 'market_value', label: 'Value', num: true, render: (x) => inr(x.market_value) },
            { key: 'unrealized_pnl', label: 'Unrealised', num: true, render: (x) => <span className={signClass(x.unrealized_pnl)}>{inr(x.unrealized_pnl)}</span> },
            { key: 'entry_date', label: 'Held since' },
          ]} />
        </section>
      </div>
    </div>
  )
}
