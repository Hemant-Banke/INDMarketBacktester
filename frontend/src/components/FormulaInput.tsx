import { useEffect, useMemo, useRef, useState } from 'react'
import { api, getCatalog, type Catalog } from '../api'

type Suggestion = { insert: string; label: string; hint: string }

/** Spreadsheet-style formula bar: metric/function autocomplete + live server validation. */
export function FormulaInput({ value, onChange, placeholder, live = false, disabled = false, autoFocus = false }: {
  value: string; onChange: (v: string) => void; placeholder?: string; live?: boolean; disabled?: boolean; autoFocus?: boolean
}) {
  const [cat, setCat] = useState<Catalog | null>(null)
  const [state, setState] = useState<{ ok: boolean; error?: string; n?: number | null; pass?: number | null } | null>(null)
  const [open, setOpen] = useState(false)
  const [sel, setSel] = useState(0)
  const [caret, setCaret] = useState(0)
  const ref = useRef<HTMLInputElement>(null)

  useEffect(() => { getCatalog().then(setCat).catch(() => {}) }, [])

  // validate (debounced)
  useEffect(() => {
    if (!value.trim()) { setState(null); return }
    const t = setTimeout(() => {
      api<{ ok: boolean; error?: string; non_missing?: number | null; passing?: number | null }>('/formula/validate', { body: { formula: value, live } })
        .then((r) => setState({ ok: r.ok, error: r.error, n: r.non_missing, pass: r.passing }))
        .catch(() => setState(null))
    }, 350)
    return () => clearTimeout(t)
  }, [value, live])

  const word = useMemo(() => {
    const left = value.slice(0, caret)
    const m = left.match(/[A-Za-z_][A-Za-z0-9_]*$/)
    return m ? m[0] : ''
  }, [value, caret])

  const suggestions: Suggestion[] = useMemo(() => {
    if (!cat || word.length < 1) return []
    const w = word.toLowerCase()
    const ms = cat.metrics.filter((m) => (live || !m.name.startsWith('tt_')) && m.name.toLowerCase().includes(w))
      .map((m) => ({ insert: m.name, label: m.name, hint: m.description, starts: m.name.toLowerCase().startsWith(w) }))
    const fs = cat.functions.filter((f) => f.signature.toLowerCase().startsWith(w))
      .map((f) => ({ insert: f.signature.split('(')[0] + '(', label: f.signature, hint: f.description, starts: true }))
    return [...fs, ...ms].sort((a, b) => Number(b.starts) - Number(a.starts)).slice(0, 40)
  }, [cat, word, live])

  const apply = (s: Suggestion) => {
    const start = caret - word.length
    const next = value.slice(0, start) + s.insert + value.slice(caret)
    onChange(next)
    setOpen(false)
    const pos = start + s.insert.length
    requestAnimationFrame(() => { ref.current?.setSelectionRange(pos, pos); ref.current?.focus() })
  }

  const cls = ['fbar', state && !state.ok ? 'bad' : '', disabled ? 'off' : ''].join(' ')
  return (
    <div className={cls}>
      <div className="fx" aria-hidden>fx</div>
      <input ref={ref} value={value} placeholder={placeholder} spellCheck={false} autoFocus={autoFocus}
        aria-label="Formula" aria-invalid={state ? !state.ok : undefined}
        onChange={(e) => { onChange(e.target.value); setCaret(e.target.selectionStart ?? 0); setOpen(true); setSel(0) }}
        onKeyUp={(e) => setCaret((e.target as HTMLInputElement).selectionStart ?? 0)}
        onClick={(e) => setCaret((e.target as HTMLInputElement).selectionStart ?? 0)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (!open || !suggestions.length) return
          if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, suggestions.length - 1)) }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)) }
          else if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); apply(suggestions[sel]) }
          else if (e.key === 'Escape') setOpen(false)
        }} />
      <div className="state" aria-live="polite">
        {state?.ok && <span className="ok" title="Formula is valid (counts are for the latest date)">✓ {state.pass != null ? `${state.pass} pass today` : state.n != null ? `${state.n} with a value` : ''}</span>}
        {state && !state.ok && <span className="err" title={state.error}>{shorten(state.error ?? 'Invalid')}</span>}
      </div>
      {open && suggestions.length > 0 && (
        <div className="suggest" role="listbox">
          {suggestions.map((s, i) => (
            <div key={s.label} role="option" aria-selected={i === sel} className={i === sel ? 'on' : ''}
              onMouseDown={(e) => { e.preventDefault(); apply(s) }}>
              <code>{s.label}</code><span>{s.hint}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function shorten(s: string) { return s.length > 46 ? s.slice(0, 44) + '…' : s }
