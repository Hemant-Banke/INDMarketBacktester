import { useEffect, useState } from 'react'
import { api } from '../api'

const STEPS: [string, string, string][] = [
  ['snapshot', 'Tickertape snapshot', "Today's Tickertape screener values, sectors and industries for every stock."],
  ['corporate_actions', 'Splits and bonuses', 'Split, bonus, rights and demerger history from Tickertape and Yahoo, used to adjust prices. About an hour (both sources throttle bulk requests).'],
  ['prices', 'Daily prices', 'NSE bhavcopies for every trading day since the start date, adjusted for splits and bonuses. First run takes about an hour (NSE throttles fast downloads); later runs fetch only new days.'],
  ['indices', 'Benchmarks', 'NIFTY 50, NIFTY 500, Bank, IT, Next 50 and Sensex history.'],
  ['fundamentals', 'Financial statements', 'Annual income, balance sheet and cash flow plus recent quarters for ~5,500 companies. Paced to avoid Tickertape blocking us, so it takes about 2 hours.'],
]

export function Data() {
  const [st, setSt] = useState<any>(null)
  const [job, setJob] = useState<any>(null)
  const [start, setStart] = useState('2005-01-01')
  const [err, setErr] = useState('')
  const load = () => api('/status').then((s: any) => { setSt(s); const running = s.jobs?.find((j: any) => j.status === 'running'); if (running) setJob(running) })
  useEffect(() => { load() }, [])
  useEffect(() => {
    if (job?.status !== 'running') return
    const t = setInterval(() => api(`/jobs/${job.id}`).then((j: any) => { setJob(j); if (j.status !== 'running') load() }), 1000)
    return () => clearInterval(t)
  }, [job?.id, job?.status])
  const run = async (steps: string[]) => {
    setErr('')
    try { const { job: id } = await api<{ job: string }>('/ingest', { body: { steps, start } }); setJob({ id, status: 'running', steps }) }
    catch (e: any) { setErr(e.message) }
  }
  if (!st) return null
  return (
    <div>
      <h1>Data</h1>
      <p className="lede">Where the numbers come from and how fresh they are.</p>
      <div className="grid2">
        <section className="panel">
          <h2>Loaded</h2>
          {st.loaded ? (
            <div className="kv">
              <div><span>Price history</span><b>{st.start} → {st.end}</b></div>
              <div><span>Sessions</span><b>{st.sessions.toLocaleString('en-IN')}</b></div>
              <div><span>Stocks ever listed</span><b>{st.symbols_total.toLocaleString('en-IN')}</b></div>
              <div><span>Trading now</span><b>{st.listed_now.toLocaleString('en-IN')}</b></div>
              <div><span>Delisted / inactive</span><b>{st.delisted_or_inactive.toLocaleString('en-IN')}</b></div>
              <div><span>Benchmarks</span><b>{st.benchmarks.join(', ') || 'none'}</b></div>
              {Object.entries(st.fundamentals ?? {}).map(([k, v]: any) => (
                <div key={k}><span>{k.replace('_', ' ')} known from</span><b>{v.first_available} ({v.companies.toLocaleString('en-IN')} cos)</b></div>
              ))}
            </div>
          ) : <p>No price data yet. Download daily prices to get started.</p>}
        </section>
        <section className="panel stack">
          <h2>Refresh</h2>
          <label className="field" style={{ maxWidth: 220 }}>Prices from<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
          {STEPS.map(([k, label, desc]) => (
            <div className="row" key={k} style={{ alignItems: 'flex-start' }}>
              <button className="btn" style={{ minWidth: 170 }} disabled={job?.status === 'running'} onClick={() => run([k])}>Update {label.toLowerCase()}</button>
              <div className="small" style={{ flex: 1, minWidth: 200 }}>{desc}
                {st.ingest?.[k] && <div className="muted">Last updated {st.ingest[k].at.replace('T', ' ')}</div>}</div>
            </div>
          ))}
          <button className="btn primary" disabled={job?.status === 'running'} onClick={() => run(STEPS.map((s) => s[0]))}>Update everything</button>
          {job && <div>
            <div className="small">{job.status === 'running' ? `Working on ${job.step ?? '…'}: ${job.message ?? ''}` : job.status === 'done' ? 'Update finished.' : 'Update failed.'}</div>
            {job.status === 'running' && <div className="progress"><div style={{ width: `${(job.progress ?? 0) * 100}%` }} /></div>}
            {job.status === 'error' && <div className="errorbox">{job.message}</div>}
          </div>}
          {err && <div className="errorbox">{err}</div>}
        </section>
      </div>
      <section className="panel" style={{ marginTop: 16 }}>
        <h2>How look-ahead is prevented</h2>
        <ul style={{ margin: 0, paddingLeft: 18, maxWidth: '80ch' }}>
          <li>A strategy decides after a session's close using only data up to that close; its orders fill at the next session's open or close.</li>
          <li>Quarterly results count as public {st.report_lag_days.quarterly} days after the quarter ends and annual results {st.report_lag_days.annual} days after the year ends (SEBI allows 45 and 60).</li>
          <li>The universe is rebuilt on every date from the stocks trading that day, including ones that later delisted. Stocks that stop trading are sold at their last price after 30 silent sessions.</li>
          <li>Tickertape's live screener fields (<code>tt_…</code>) are today's values, so the backtester refuses them.</li>
          <li>A test suite reruns each example strategy on history cut short and checks every trade matches the full-history run.</li>
        </ul>
        <h2 style={{ marginTop: 16 }}>Known limits</h2>
        <ul style={{ margin: 0, paddingLeft: 18, maxWidth: '80ch' }}>
          <li>Tickertape's free tier serves about five fiscal years and five quarters of statements, so fundamental strategies only have data from roughly mid-2022. Refreshing regularly builds the history up over time.</li>
          <li>Statements are as currently reported; later restatements replace the original numbers.</li>
          <li>Prices are not adjusted for dividends, and the benchmarks are price indices, so both sides of the comparison exclude dividends.</li>
          <li>Sector labels are today's classification.</li>
        </ul>
      </section>
    </div>
  )
}
