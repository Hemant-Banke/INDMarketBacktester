import { useEffect, useState } from 'react'
import { api } from '../api'
import type { StrategyInfo } from './Backtest'

type Guide = { overview: string; ctx: { name: string; signature: string; doc: string }[] }

export function Strategies({ go }: { go: (h: string) => void }) {
  const [list, setList] = useState<StrategyInfo[]>([])
  const [file, setFile] = useState<string | null>(null)
  const [src, setSrc] = useState('')
  const [dirty, setDirty] = useState(false)
  const [msg, setMsg] = useState('')
  const [guide, setGuide] = useState<Guide | null>(null)
  const [newName, setNewName] = useState('')

  const load = () => api<StrategyInfo[]>('/strategies').then(setList)
  useEffect(() => { load(); api<Guide>('/strategy-guide').then(setGuide) }, [])
  const open = async (f: string) => {
    const r = await api<{ source: string }>(`/strategies/${f}/source`)
    setFile(f); setSrc(r.source); setDirty(false); setMsg('')
  }
  const save = async () => {
    try {
      await api(`/strategies/${file}/source`, { method: 'PUT', body: { source: src } })
      setDirty(false); setMsg('Saved.'); load()
    } catch (e: any) { setMsg(e.message) }
  }
  const create = async () => {
    const f = (newName.trim() || 'my_strategy').replace(/\W+/g, '_').replace(/\.py$/, '') + '.py'
    try { await api(`/strategies/${f}`, { method: 'POST' }); await load(); open(f); setNewName('') } catch (e: any) { setMsg(e.message) }
  }
  const files = [...new Set(list.map((s) => s.file))]

  return (
    <div>
      <h1>Strategies</h1>
      <p className="lede">A strategy is a Python class in the <code>strategies/</code> folder. Edit them here or in your own editor — the list reloads every time you open it.</p>
      <div className="grid2" style={{ gridTemplateColumns: 'minmax(260px, 1fr) minmax(0, 2.4fr)' }}>
        <div className="stack">
          <section className="panel stack" style={{ gap: 10 }}>
            {list.map((s) => (
              <div key={s.id} style={{ borderBottom: '1px solid var(--rule)', paddingBottom: 10 }}>
                <div className="row"><b>{s.name}</b><span className="spacer" />
                  <button className="btn small" onClick={() => open(s.file)}>Edit</button>
                  {!s.error && <button className="btn small" onClick={() => go('#/backtest')}>Backtest</button>}</div>
                <div className="small muted">{s.description}</div>
                <div className="small muted"><code>{s.file}</code> · {String(s.schedule)}</div>
                {s.error && <div className="errorbox" style={{ marginTop: 6 }}>{s.error}</div>}
              </div>
            ))}
            <div className="row">
              <input type="text" placeholder="new_strategy" value={newName} onChange={(e) => setNewName(e.target.value)} />
              <button className="btn" onClick={create}>New from template</button>
            </div>
          </section>
          {guide && (
            <section className="panel">
              <h2>What <code>ctx</code> gives you</h2>
              {guide.ctx.map((m) => (
                <div key={m.name} style={{ marginBottom: 8 }}>
                  <code>ctx.{m.name}{m.signature}</code>
                  {m.doc && <div className="small muted" style={{ whiteSpace: 'pre-wrap' }}>{m.doc}</div>}
                </div>
              ))}
            </section>
          )}
        </div>
        <section className="panel stack">
          {file ? <>
            <div className="row"><h2 style={{ margin: 0 }}><code>{file}</code></h2><span className="spacer" />
              {msg && <span className="small muted">{msg}</span>}
              <button className="btn primary" onClick={save} disabled={!dirty}>Save</button></div>
            <textarea className="editor" spellCheck={false} value={src}
              onChange={(e) => { setSrc(e.target.value); setDirty(true) }}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); save() }
                if (e.key === 'Tab') {
                  e.preventDefault()
                  const el = e.currentTarget, a = el.selectionStart, b = el.selectionEnd
                  const next = src.slice(0, a) + '    ' + src.slice(b)
                  setSrc(next); setDirty(true)
                  requestAnimationFrame(() => el.setSelectionRange(a + 4, a + 4))
                }
              }} />
          </> : <>
            <h2>How a strategy runs</h2>
            <pre className="mono small" style={{ whiteSpace: 'pre-wrap', color: 'var(--ink-2)' }}>{guide?.overview}</pre>
            {files.length > 0 && <p className="small muted">Pick a strategy on the left to edit it.</p>}
          </>}
        </section>
      </div>
    </div>
  )
}
