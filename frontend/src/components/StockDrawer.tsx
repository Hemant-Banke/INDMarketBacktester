import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { cell } from '../format'
import { axisStyle, baseOption, Chart, useTheme } from './Chart'

type Stock = {
  symbol: string; name: string; sector: string; industry: string
  prices: [string, number, number][]; metrics: Record<string, number | null>
}

const LABELS: Record<string, [string, string?]> = {
  mcap: ['Market cap (Cr)'], pe: ['P/E'], pb: ['P/B'], ps: ['P/S'], ev_ebitda: ['EV/EBITDA'],
  roe: ['ROE', '%'], roce: ['ROCE', '%'], net_margin: ['Net margin', '%'], debt_equity: ['Debt/equity'],
  div_yield: ['Dividend yield', '%'], revenue: ['Revenue (Cr)'], net_income: ['Net profit (Cr)'],
  revenue_growth: ['Revenue growth', '%'], eps_growth: ['EPS growth', '%'], ret_1m: ['1M return', '%'],
  ret_6m: ['6M return', '%'], ret_1y: ['1Y return', '%'], vol_1y: ['Volatility 1Y', '%'], beta_1y: ['Beta 1Y'],
  adv_20d: ['Avg traded value 20D (Cr)'], pct_from_52w_high: ['From 52W high', '%'],
}

export function StockDrawer({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const [s, setS] = useState<Stock | null>(null)
  const [err, setErr] = useState('')
  const t = useTheme()
  useEffect(() => { setS(null); api<Stock>(`/stock/${encodeURIComponent(symbol)}`).then(setS).catch((e) => setErr(e.message)) }, [symbol])
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [onClose])
  const option = useMemo(() => s && ({
    ...baseOption(t),
    xAxis: { type: 'time', ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'log', scale: true, ...axisStyle(t) },
    dataZoom: [{ type: 'inside' }],
    series: [{ type: 'line', showSymbol: false, lineStyle: { width: 1.5, color: t.accent }, itemStyle: { color: t.accent },
      data: s.prices.map((p) => [p[0], p[1]]), name: 'Close (adjusted)' }],
  }), [s, t])
  return (
    <aside className="drawer" aria-label={`${symbol} details`}>
      <div className="row"><h2 style={{ margin: 0 }}>{symbol}</h2><span className="spacer" /><button className="btn ghost" onClick={onClose}>Close</button></div>
      {err && <div className="errorbox">{err}</div>}
      {s && <>
        <p className="lede" style={{ margin: '4px 0 12px' }}>{s.name} — {s.sector} / {s.industry}</p>
        {option && <Chart option={option} />}
        <p className="small muted">Close adjusted for splits and bonuses. Scroll on the chart to zoom.</p>
        <h3 style={{ marginTop: 16 }}>Latest metrics</h3>
        <div className="kv">
          {Object.entries(LABELS).map(([k, [label, unit]]) => (
            <div key={k}><span>{label}</span><b>{cell(s.metrics[k], unit)}</b></div>
          ))}
        </div>
      </>}
    </aside>
  )
}
