import { useEffect, useState } from 'react'
import { Backtest } from './pages/Backtest'
import { Data } from './pages/Data'
import { RunDetail, RunList } from './pages/Results'
import { Screener } from './pages/Screener'
import { Strategies } from './pages/Strategies'

const NAV: [string, string][] = [['#/screener', 'Screener'], ['#/backtest', 'Backtest'], ['#/results', 'Results'], ['#/strategies', 'Strategies'], ['#/data', 'Data']]

export default function App() {
  const [hash, setHash] = useState(location.hash || '#/screener')
  useEffect(() => {
    const on = () => setHash(location.hash || '#/screener')
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const go = (h: string) => { location.hash = h }
  const [, page, arg] = hash.split('/')
  return (
    <div className="shell">
      <nav className="rail" aria-label="Main">
        <div className="brand">Markets Backtester<small>NSE · point-in-time</small></div>
        {NAV.map(([h, l]) => <a key={h} href={h} className={hash.startsWith(h) ? 'on' : ''}>{l}</a>)}
        <div className="foot">Prices: NSE bhavcopy<br />Fundamentals: Tickertape</div>
      </nav>
      <main>
        {page === 'screener' && <Screener />}
        {page === 'backtest' && <Backtest go={go} />}
        {page === 'results' && (arg ? <RunDetail id={arg} /> : <RunList go={go} />)}
        {page === 'strategies' && <Strategies go={go} />}
        {page === 'data' && <Data />}
      </main>
    </div>
  )
}
