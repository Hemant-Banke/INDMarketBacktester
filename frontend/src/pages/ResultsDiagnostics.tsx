import { useMemo, useState } from 'react'
import { axisStyle, baseOption, Chart, useTheme } from '../components/Chart'
import { DataTable } from '../components/DataTable'
import { inr, num, pct, signClass } from '../format'
import { KV, lineSeries, Tip } from './Results'

// ---------------- costs and tax

const COMPONENT_LABEL: Record<string, string> = {
  stt: 'STT', slippage: 'Slippage', stamp: 'Stamp duty', exchange: 'Exchange charges', dp: 'DP charges',
  gst: 'GST', sebi: 'SEBI fee', brokerage: 'Brokerage',
}

export function Costs({ r }: { r: any }) {
  const t = useTheme()
  const c = r.costs
  const [log, setLog] = useState(true)
  const growth = useMemo(() => ({
    ...baseOption(t),
    tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => inr(v) },
    xAxis: { type: 'time', ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: log ? 'log' : 'value', scale: true, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => inr(v) } },
    dataZoom: [{ type: 'inside' }],
    series: [
      lineSeries('Before costs and tax', c.charts.equity_gross, t.bench, 1.5, { lineStyle: { width: 1.5, color: t.bench, type: 'dashed' } }),
      lineSeries('After trading costs', c.charts.equity_pre_tax, t.accent, 1.5, { lineStyle: { width: 1.5, color: t.accent, opacity: 0.55 } }),
      lineSeries('After costs and tax', c.charts.equity_after_tax, t.accent, 2),
    ],
  }), [c, t, log])
  const cum = useMemo(() => ({
    ...baseOption(t),
    tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => inr(v) },
    xAxis: { type: 'time', ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => inr(v) } },
    series: [
      lineSeries('Charges and taxes on trades', c.charts.cum_fees, t.accent, 1.5),
      lineSeries('Slippage', c.charts.cum_slippage, t.bench, 1.5),
      lineSeries('Capital-gains tax', c.charts.cum_tax, t.neg, 1.5),
    ],
  }), [c, t])
  const total = c.total_trading_costs + c.total_tax
  const comps = [...Object.entries(c.components as Record<string, number>).map(([k, v]) => ({ k, v })), { k: 'tax', v: c.total_tax }]
    .filter((x) => x.v > 0).sort((a, b) => b.v - a.v)
  const end = c.end_taxes ?? {}
  const pt = c.per_trade ?? {}
  const ladder = [
    ['Before any costs or tax', c.cagr_before_costs],
    ['After trading costs (charges + slippage)', c.cagr_after_costs],
    [c.tax_mode === 'pay' ? 'After costs and tax (the backtest)' : 'After costs and tax (estimated)', c.cagr_after_tax],
    ['After tax, if everything were sold on the last day', c.cagr_after_tax_liquidation],
  ] as [string, number][]
  return (
    <div className="stack">
      {c.tax_mode !== 'pay' && <div className="note warn">Capital-gains tax was only reported for this run, not deducted. The equity curve and headline numbers are before tax.</div>}
      <div className="grid2">
        <section className="panel">
          <h2>CAGR at each stage</h2>
          <table className="data compare">
            <thead><tr><th></th><th className="num">CAGR</th><th className="num">Cost of this step</th></tr></thead>
            <tbody>{ladder.map(([l, v], i) => (
              <tr key={l}><td><Tip label={l} /></td><td className="num"><b>{pct(v, 2)}</b></td>
                <td className="num">{i === 0 ? '' : <span className="neg">{pct(v - ladder[i - 1][1], 2, true)}</span>}</td></tr>
            ))}</tbody>
          </table>
          <p className="small muted">Costs are added back day by day as a return on the previous day's equity, so the “before” figures are close estimates, not separate runs.</p>
        </section>
        <section className="panel stack">
          <div><h2>Totals</h2><KV rows={[
            ['Trading costs', inr(c.total_trading_costs)], ['Capital-gains tax', inr(c.total_tax)],
            ['Value traded', inr(c.traded_value)], ['Cost per ₹ traded', `${num(c.cost_pct_of_traded_bps, 1)} bps`],
            ['Round-trip cost', `${num(pt.avg_round_trip_cost_bps, 0)} bps`], ['Average trade size', inr(pt.avg_trade_value)],
            ['Median trade return', `${num(pt.median_gross_trade_return_pct, 2)}%`], ['Average trade return', `${num(pt.avg_gross_trade_return_pct, 2)}%`],
          ]} /></div>
          <div><h2>At the end ({end.fy ?? '–'} so far)</h2><KV rows={[
            ['Tax accrued, not yet paid', inr(end.accrued_tax)], ['Tax if sold everything', inr(end.liquidation_tax)],
            ['Selling costs if sold everything', inr(end.liquidation_costs)], ['Value after selling and tax', inr(end.liquidation_value)],
            ['Losses carried forward', inr(end.losses_carried_forward)],
          ]} /></div>
        </section>
      </div>
      <section className="panel">
        <div className="row"><h2 style={{ margin: 0 }}>Growth before and after costs</h2><span className="spacer" />
          <div className="legend"><span><i style={{ background: t.bench }} />Before costs and tax</span><span><i style={{ background: t.accent, opacity: 0.55 }} />After trading costs</span><span><i style={{ background: t.accent }} />After costs and tax</span></div>
          <div className="seg"><button className={log ? 'on' : ''} onClick={() => setLog(true)}>Log</button><button className={!log ? 'on' : ''} onClick={() => setLog(false)}>Linear</button></div>
        </div>
        <Chart option={growth as any} className="chart tall" />
      </section>
      <div className="grid2">
        <section className="panel">
          <h2>Where the money went</h2>
          <DataTable rows={comps} cols={[
            { key: 'k', label: 'Item', render: (x) => x.k === 'tax' ? 'Capital-gains tax' : COMPONENT_LABEL[x.k] ?? x.k },
            { key: 'v', label: 'Amount', num: true, render: (x) => inr(x.v) },
            { key: 'share', label: 'Share', num: true, value: (x) => x.v / total, render: (x) => pct(x.v / total, 1) },
            { key: 'bps', label: 'bps of value traded', num: true, value: (x) => x.v / c.traded_value, render: (x) => x.k === 'tax' ? '–' : num(x.v / c.traded_value * 1e4, 2) },
          ]} />
        </section>
        <section className="panel"><h2>Cumulative costs</h2><Chart option={cum as any} className="chart short" /></section>
      </div>
      <section className="panel">
        <h2>Costs by calendar year</h2>
        <DataTable rows={c.by_year} cols={[
          { key: 'year', label: 'Year' },
          { key: 'turnover', label: 'Turnover', num: true, render: (x) => pct(x.turnover, 0) },
          { key: 'fees', label: 'Charges', num: true, render: (x) => inr(x.fees) },
          { key: 'slippage', label: 'Slippage', num: true, render: (x) => inr(x.slippage) },
          { key: 'trading_cost_pct', label: 'Trading costs % of equity', num: true, render: (x) => pct(x.trading_cost_pct, 2) },
          { key: 'tax', label: 'Tax paid', num: true, render: (x) => inr(x.tax) },
          { key: 'tax_pct', label: 'Tax % of equity', num: true, render: (x) => pct(x.tax_pct, 2) },
          { key: 'return_pre_cost', label: 'Return before costs', num: true, render: (x) => <span className={signClass(x.return_pre_cost)}>{pct(x.return_pre_cost)}</span> },
          { key: 'return_after_cost', label: 'After costs', num: true, render: (x) => <span className={signClass(x.return_after_cost)}>{pct(x.return_after_cost)}</span> },
          { key: 'return_after_tax', label: 'After tax', num: true, render: (x) => <span className={signClass(x.return_after_tax)}>{pct(x.return_after_tax)}</span> },
        ]} />
      </section>
      <section className="panel">
        <h2>Capital-gains tax by financial year</h2>
        <p className="small muted" style={{ marginTop: -4 }}>
          Rates as on each sale date: equity STCG 15% (20% from 23 Jul 2024), LTCG after 12 months 10% above ₹1 lakh from FY 2018-19 (12.5% above ₹1.25 lakh from 23 Jul 2024), exempt before; grandfathered cost for shares bought by 31 Jan 2018. Gold, debt and foreign ETFs follow their own rules (slab rate, indexation). Short-term losses offset any gain, long-term losses only long-term gains; unused losses carry forward 8 years. STT is not deductible. Tax plus cess (and the surcharge you set) is paid on the first session of the next financial year, selling holdings pro rata if cash is short.
        </p>
        <DataTable rows={c.tax_years} cols={[
          { key: 'fy', label: 'FY' },
          { key: 'stcg', label: 'ST gains', num: true, render: (x) => inr(x.stcg) },
          { key: 'st_losses', label: 'ST losses', num: true, render: (x) => inr(x.st_losses) },
          { key: 'ltcg', label: 'LT gains', num: true, render: (x) => inr(x.ltcg) },
          { key: 'lt_losses', label: 'LT losses', num: true, render: (x) => inr(x.lt_losses) },
          { key: 'carried_losses_used', label: 'Old losses used', num: true, render: (x) => inr(x.carried_losses_used) },
          { key: 'ltcg_exemption_used', label: 'LTCG exemption', num: true, render: (x) => inr(x.ltcg_exemption_used) },
          { key: 'taxable', label: 'Taxable', num: true, value: (x) => x.taxable_st + x.taxable_lt, render: (x) => inr(x.taxable_st + x.taxable_lt) },
          { key: 'tax', label: 'Tax', num: true, render: (x) => <b>{inr(x.tax)}</b> },
          { key: 'losses_carried_forward', label: 'Losses carried', num: true, render: (x) => inr(x.losses_carried_forward) },
          { key: 'paid_on', label: c.tax_mode === 'pay' ? 'Paid on' : 'Due on' },
        ]} />
      </section>
      <section className="panel">
        <h2>Gains by tax treatment</h2>
        <DataTable rows={c.tax_classes} empty="No position was closed." cols={[
          { key: 'class', label: 'Treatment' }, { key: 'round_trips', label: 'Round trips', num: true },
          { key: 'gains', label: 'Gains', num: true, render: (x) => inr(x.gains) },
          { key: 'losses', label: 'Losses', num: true, render: (x) => inr(x.losses) },
          { key: 'net', label: 'Net', num: true, render: (x) => <span className={signClass(x.net)}>{inr(x.net)}</span> },
          { key: 'median_sessions_held', label: 'Median sessions held', num: true, render: (x) => num(x.median_sessions_held, 0) },
        ]} />
      </section>
    </div>
  )
}

// ---------------- robustness

type Check = { name: string; value: string; level: 'ok' | 'warn' | 'bad'; reading: string }

function grade(v: number | null | undefined, ok: (v: number) => boolean, warn: (v: number) => boolean): Check['level'] {
  if (typeof v !== 'number' || !Number.isFinite(v)) return 'warn'
  return ok(v) ? 'ok' : warn(v) ? 'warn' : 'bad'
}

function checks(r: any): Check[] {
  const rb = r.robustness
  const con = rb.concentration
  const sig = rb.significance ?? {}
  const bs = rb.bootstrap ?? {}
  const bcagr = r.summary.benchmark.cagr
  const out: Check[] = []
  if (con) {
    const top = con.top?.[0]
    out.push({ name: 'Biggest single contributor', value: `${top?.symbol}: ${pct(con.top1_share, 0)} of net profit`,
      level: grade(con.top1_share, (v) => v < 0.2, (v) => v < 0.4),
      reading: 'Under 20% means no one holding carried the result.' })
    const ex5 = con.cagr_excluding_top.find((x: any) => x.removed === 5)
    if (ex5) out.push({ name: 'CAGR without the 5 best names', value: `${pct(ex5.cagr)} (vs ${pct(con.base_cagr)})`,
      level: grade(ex5.cagr - (bcagr ?? 0), (v) => v > 0.03, (v) => v > 0),
      reading: 'Their daily P&L is removed as if that money had sat idle. Still beating the benchmark means the edge is spread out.' })
    out.push({ name: 'Names needed for half the profit', value: `${con.names_for_profit_share['50%']} of ${con.symbols_traded} traded`,
      level: grade(con.names_for_profit_share['50%'], (v) => v >= 20, (v) => v >= 8), reading: 'More names means a broader, more repeatable edge.' })
  }
  if (sig.alpha_t_stat !== undefined) out.push({ name: 'Alpha t-statistic', value: `${num(sig.alpha_t_stat, 2)} (alpha ${pct(sig.alpha_annual)} a year)`,
    level: grade(sig.alpha_t_stat, (v) => v >= 2.5, (v) => v >= 1.5), reading: 'Above 2 means the excess return is unlikely to be chance (daily returns, no correction for testing many variants).' })
  out.push({ name: 'Probabilistic Sharpe', value: pct(sig.probabilistic_sharpe, 1),
    level: grade(sig.probabilistic_sharpe, (v) => v >= 0.95, (v) => v >= 0.8), reading: 'Chance the true Sharpe is above 0, allowing for skew and fat tails.' })
  if (bs.cagr_p5 !== undefined) out.push({ name: 'Bootstrap CAGR, 5th–95th percentile', value: `${pct(bs.cagr_p5)} to ${pct(bs.cagr_p95)}`,
    level: grade(bs.cagr_p5 - (bcagr ?? 0), (v) => v > 0, (v) => v > -0.03), reading: 'History reshuffled in monthly blocks 1,000 times. A low end above the benchmark is a strong sign.' })
  if (bs.prob_beats_benchmark !== undefined) out.push({ name: 'Bootstrap chance of beating the benchmark', value: pct(bs.prob_beats_benchmark, 1),
    level: grade(bs.prob_beats_benchmark, (v) => v >= 0.9, (v) => v >= 0.7), reading: 'Share of reshuffled histories in which the strategy ended ahead.' })
  const sub = rb.subperiods ?? []
  if (sub.length && sub[0].benchmark_cagr !== undefined) {
    const wins = sub.filter((x: any) => x.cagr > x.benchmark_cagr).length
    out.push({ name: 'Beat the benchmark in each third of the period', value: `${wins} of ${sub.length}`,
      level: wins === sub.length ? 'ok' : wins >= sub.length - 1 ? 'warn' : 'bad', reading: 'An edge that only shows up in one stretch may belong to that market, not the strategy.' })
  }
  const r3 = (rb.rolling_consistency ?? []).find((x: any) => x.years === 3)
  if (r3?.beat_benchmark !== undefined) out.push({ name: '3-year windows ahead of the benchmark', value: pct(r3.beat_benchmark, 0),
    level: grade(r3.beat_benchmark, (v) => v >= 0.75, (v) => v >= 0.55), reading: `Worst 3-year CAGR ${pct(r3.worst_cagr)}.` })
  const ex = rb.execution
  if (ex) {
    out.push({ name: 'Size of fills vs volume (95th percentile)', value: pct(ex.participation_p95, 1),
      level: grade(ex.participation_p95, (v) => v <= 0.05, (v) => v <= 0.1), reading: 'Above ~5% of a day’s volume, real fills would likely move the price more than the slippage assumed.' })
    const vol = (ex.expired_by_cause ?? []).filter((x: any) => x.cause === 'volume' || x.cause === 'no price')
    const v = vol.reduce((a: number, x: any) => a + x.value, 0)
    out.push({ name: 'Orders that never filled (illiquid / no trades)', value: `${vol.reduce((a: number, x: any) => a + x.orders, 0)} orders, ${inr(v)}`,
      level: v < 0.05 * r.summary.portfolio.final_equity ? 'ok' : 'warn', reading: 'Unfilled sells mean the backtest held stocks it wanted to exit. Cash-limited buys are not counted here.' })
    if (ex.delisted_exits) out.push({ name: 'Exits from suspended or delisted stocks', value: `${ex.delisted_exits}, ${inr(ex.delisted_value)}`,
      level: 'warn', reading: 'Booked at the last traded price with no haircut, which flatters results. Set a delisting haircut in the backtest settings to test.' })
  }
  const types = con?.by_asset_type ?? []
  const nonStock = types.filter((x: any) => x.type !== 'Stocks')
  for (const x of nonStock) out.push({ name: `Profit from ${x.type.toLowerCase()}`, value: `${pct(x.share_of_net, 0)} of net, CAGR without: ${pct(x.cagr_without)}`,
    level: grade(x.share_of_net, (v) => v < 0.15, (v) => v < 0.35), reading: 'A large share means part of the result is a bet on that asset (e.g. gold’s run), not stock selection.' })
  return out
}

const DOT: Record<Check['level'], string> = { ok: 'var(--good)', warn: 'var(--warning)', bad: 'var(--critical)' }

export function Robustness({ r, onSymbol }: { r: any; onSymbol: (s: string) => void }) {
  const t = useTheme()
  const rb = r.robustness
  const con = rb.concentration
  const sig = rb.significance ?? {}
  const bs = rb.bootstrap ?? {}
  const ex = rb.execution ?? {}
  const bcagr = r.summary.benchmark.cagr
  const exclOpt = useMemo(() => {
    if (!con) return null
    const rows = [{ removed: 0, cagr: con.base_cagr }, ...con.cagr_excluding_top]
    return {
      ...baseOption(t), legend: { show: false },
      tooltip: { ...baseOption(t).tooltip, valueFormatter: (v: any) => pct(v) },
      xAxis: { type: 'category', data: rows.map((x) => x.removed === 0 ? 'All' : `−${x.removed}`), ...axisStyle(t), splitLine: { show: false }, name: 'best names removed', nameLocation: 'middle', nameGap: 28, nameTextStyle: { color: t.ink3 } },
      yAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => pct(v, 0) } },
      series: [{ type: 'bar', name: 'CAGR', data: rows.map((x) => x.cagr), itemStyle: { color: t.accent, borderRadius: [4, 4, 0, 0] },
        markLine: bcagr == null ? undefined : { silent: true, symbol: 'none', lineStyle: { color: t.bench, type: 'dashed' }, label: { formatter: 'Benchmark', color: t.ink3 }, data: [{ yAxis: bcagr }] } }],
    }
  }, [con, t, bcagr])
  const list = checks(r)
  return (
    <div className="stack">
      <section className="panel">
        <h2>Checks</h2>
        <p className="small muted" style={{ marginTop: -4 }}>Is the result a broad, repeatable edge, or a few lucky holdings and one good stretch? Green passes, amber deserves a look, red is a warning sign. Thresholds are rules of thumb.</p>
        <div className="tablewrap">
          <table className="data">
            <thead><tr><th></th><th>Check</th><th>Result</th><th>What it tells you</th></tr></thead>
            <tbody>{list.map((c) => (
              <tr key={c.name}>
                <td><i aria-label={c.level} style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: DOT[c.level] }} /></td>
                <td>{c.name}</td><td style={{ whiteSpace: 'nowrap' }}><b>{c.value}</b></td><td className="small muted">{c.reading}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>
      {con && <>
        <div className="grid2">
          <section className="panel">
            <h2>CAGR with the best names removed</h2>
            <p className="small muted" style={{ marginTop: -4 }}>Each removed name's daily P&L is taken out, as if that money had earned nothing.</p>
            <Chart option={exclOpt as any} className="chart short" />
            <p className="small muted">Removed in this order: {con.cagr_excluding_top.slice(-1)[0]?.symbols.join(', ')}</p>
          </section>
          <section className="panel stack">
            <div><h2>Profit concentration</h2><KV rows={[
              ['Net P&L', inr(con.net_pnl)], ['Names traded', `${con.symbols_traded} (${con.symbols_profitable} profitable)`],
              ['Top 1 share', pct(con.top1_share, 0)], ['Top 5 share', pct(con.top5_share, 0)], ['Top 10 share', pct(con.top10_share, 0)],
              ['Names for 50% of profit', String(con.names_for_profit_share['50%'])], ['Names for 80% of profit', String(con.names_for_profit_share['80%'])],
            ]} /></div>
            <DataTable rows={con.by_asset_type} cols={[
              { key: 'type', label: 'Asset type' }, { key: 'symbols', label: 'Names', num: true },
              { key: 'pnl', label: 'P&L', num: true, render: (x) => <span className={signClass(x.pnl)}>{inr(x.pnl)}</span> },
              { key: 'share_of_net', label: 'Share', num: true, render: (x) => pct(x.share_of_net, 0) },
              { key: 'cagr_without', label: 'CAGR without', num: true, render: (x) => pct(x.cagr_without) },
            ]} />
          </section>
        </div>
        <div className="grid2">
          <section className="panel"><h2>Top contributors</h2>
            <DataTable rows={con.top} onRow={(x) => onSymbol(x.symbol)} cols={[
              { key: 'symbol', label: 'Symbol', render: (x) => <b>{x.symbol}</b> }, { key: 'type', label: 'Type' },
              { key: 'pnl', label: 'P&L', num: true, render: (x) => inr(x.pnl) },
              { key: 'share_of_net', label: 'Share of net', num: true, render: (x) => pct(x.share_of_net, 1) },
            ]} />
          </section>
          <section className="panel"><h2>P&L by sector</h2>
            <DataTable rows={con.by_sector} cols={[
              { key: 'sector', label: 'Sector' }, { key: 'symbols', label: 'Names', num: true },
              { key: 'pnl', label: 'P&L', num: true, render: (x) => <span className={signClass(x.pnl)}>{inr(x.pnl)}</span> },
              { key: 'share_of_net', label: 'Share', num: true, render: (x) => pct(x.share_of_net, 0) },
              { key: 'best', label: 'Best name', render: (x) => `${x.best} (${inr(x.best_pnl)})` },
            ]} />
          </section>
        </div>
        <section className="panel">
          <h2>Each year: who made the money</h2>
          <DataTable rows={con.by_year} cols={[
            { key: 'year', label: 'Year' },
            { key: 'return', label: 'Return', num: true, render: (x) => <span className={signClass(x.return)}>{pct(x.return)}</span> },
            { key: 'symbols', label: 'Names', num: true },
            { key: 'top', label: 'Best name', render: (x) => <>{x.top} <span className="muted">{inr(x.top_pnl)}</span></> },
            { key: 'top_share_of_profits', label: 'Its share of profits', num: true, render: (x) => pct(x.top_share_of_profits, 0) },
            { key: 'top5_share_of_profits', label: 'Top 5 share', num: true, render: (x) => pct(x.top5_share_of_profits, 0) },
            { key: 'worst', label: 'Worst name', render: (x) => <>{x.worst} <span className="muted">{inr(x.worst_pnl)}</span></> },
          ]} />
        </section>
      </>}
      <div className="grid2">
        <section className="panel"><h2>Statistical confidence</h2><KV rows={[
          ['Sharpe t-statistic', num(sig.sharpe_t_stat, 2)], ['Probabilistic Sharpe', pct(sig.probabilistic_sharpe, 1)],
          ['Sharpe 95% range', sig.sharpe_ci95 ? `${num(sig.sharpe_ci95[0], 2)} to ${num(sig.sharpe_ci95[1], 2)}` : '–'],
          ['Alpha t-statistic', num(sig.alpha_t_stat, 2)], ['Excess return t-statistic', num(sig.active_return_t_stat, 2)],
        ]} />
          <p className="small muted">These treat this backtest as the only one tried. After testing many variants, the best one's statistics are inflated, so ask for more than t = 2.</p>
        </section>
        <section className="panel"><h2>Block bootstrap ({bs.n ?? 0} resamples)</h2><KV rows={[
          ['CAGR 5th percentile', pct(bs.cagr_p5)], ['CAGR median', pct(bs.cagr_p50)], ['CAGR 95th percentile', pct(bs.cagr_p95)],
          ['Typical max drawdown', pct(bs.max_dd_p50)], ['Bad-case max drawdown', pct(bs.max_dd_p5)],
          ['Chance CAGR < 15%', pct(bs.prob_cagr_below_15, 1)], ['Chance of beating benchmark', pct(bs.prob_beats_benchmark, 1)],
          ['Excess CAGR 5th percentile', pct(bs.excess_cagr_p5)],
        ]} /></section>
      </div>
      <div className="grid2">
        <section className="panel"><h2>Thirds of the period</h2>
          <DataTable rows={rb.subperiods} cols={[
            { key: 'start', label: 'From' }, { key: 'end', label: 'To' },
            { key: 'cagr', label: 'CAGR', num: true, render: (x) => <span className={signClass(x.cagr)}>{pct(x.cagr)}</span> },
            { key: 'benchmark_cagr', label: 'Benchmark', num: true, render: (x) => pct(x.benchmark_cagr) },
            { key: 'sharpe', label: 'Sharpe', num: true, render: (x) => num(x.sharpe) },
            { key: 'max_drawdown', label: 'Max DD', num: true, render: (x) => pct(x.max_drawdown) },
          ]} />
        </section>
        <section className="panel"><h2>Every rolling window</h2>
          <DataTable rows={rb.rolling_consistency} cols={[
            { key: 'years', label: 'Window', render: (x) => `${x.years} year${x.years > 1 ? 's' : ''}` },
            { key: 'positive', label: 'Positive', num: true, render: (x) => pct(x.positive, 0) },
            { key: 'beat_benchmark', label: 'Beat benchmark', num: true, render: (x) => pct(x.beat_benchmark, 0) },
            { key: 'worst_cagr', label: 'Worst CAGR', num: true, render: (x) => pct(x.worst_cagr) },
            { key: 'median_cagr', label: 'Median', num: true, render: (x) => pct(x.median_cagr) },
            { key: 'worst_excess', label: 'Worst vs benchmark', num: true, render: (x) => pct(x.worst_excess, 1, true) },
          ]} />
        </section>
      </div>
      <div className="grid2">
        <section className="panel"><h2>Trades by year</h2>
          <DataTable rows={rb.trades_by_year ?? []} cols={[
            { key: 'year', label: 'Year' }, { key: 'round_trips', label: 'Round trips', num: true },
            { key: 'win_rate', label: 'Win rate', num: true, render: (x) => pct(x.win_rate, 0) },
            { key: 'avg_return_pct', label: 'Avg return', num: true, render: (x) => <span className={signClass(x.avg_return_pct)}>{num(x.avg_return_pct, 1)}%</span> },
            { key: 'profit_factor', label: 'Profit factor', num: true, render: (x) => num(x.profit_factor) },
          ]} />
        </section>
        <section className="panel stack">
          <div><h2>Execution realism</h2><KV rows={[
            ['Median fill vs volume', pct(ex.participation_median, 2)], ['95th pct fill vs volume', pct(ex.participation_p95, 1)],
            ['Largest fill vs volume', pct(ex.participation_max, 1)], ['Fills over 1% of volume', pct(ex.fills_over_1pct_volume, 0)],
            ['Fills cut by volume cap', num(ex.fills_capped, 0)], ['Delisted exits', `${num(ex.delisted_exits, 0)} (${inr(ex.delisted_value)})`],
          ]} /></div>
          <div><h3 className="small muted" style={{ margin: '0 0 6px' }}>Orders that expired unfilled</h3>
            <DataTable rows={ex.expired_by_cause ?? []} empty="Every order filled." cols={[
              { key: 'cause', label: 'Cause', render: (x) => ({ cash: 'Not enough cash', volume: 'Volume cap', 'no price': 'No trades' } as any)[x.cause] ?? x.cause },
              { key: 'side', label: 'Side' }, { key: 'orders', label: 'Orders', num: true },
              { key: 'value', label: 'Unfilled value', num: true, render: (x) => inr(x.value) },
            ]} /></div>
        </section>
      </div>
    </div>
  )
}
