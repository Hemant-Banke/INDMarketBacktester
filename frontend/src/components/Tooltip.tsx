import { useEffect, useRef, useState } from 'react'

/** One floating tooltip for every element with a data-tip attribute (hover or keyboard focus). */
export function Tooltip() {
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const show = (e: Event) => {
      const el = (e.target as HTMLElement | null)?.closest?.('[data-tip]') as HTMLElement | null
      if (!el) return
      const r = el.getBoundingClientRect()
      setTip({ text: el.dataset.tip!, x: r.left + r.width / 2, y: r.bottom })
    }
    const hide = (e: Event) => {
      const el = (e.target as HTMLElement | null)?.closest?.('[data-tip]')
      const to = (e as MouseEvent).relatedTarget as HTMLElement | null
      if (el && !(to && el.contains(to))) setTip(null)
    }
    const clear = () => setTip(null)
    document.addEventListener('mouseover', show)
    document.addEventListener('focusin', show)
    document.addEventListener('mouseout', hide)
    document.addEventListener('focusout', hide)
    window.addEventListener('scroll', clear, true)
    return () => {
      document.removeEventListener('mouseover', show)
      document.removeEventListener('focusin', show)
      document.removeEventListener('mouseout', hide)
      document.removeEventListener('focusout', hide)
      window.removeEventListener('scroll', clear, true)
    }
  }, [])
  // Keep the box inside the viewport.
  const [pos, setPos] = useState({ left: 0, top: 0 })
  useEffect(() => {
    if (!tip || !box.current) return
    const w = box.current.offsetWidth, h = box.current.offsetHeight
    const left = Math.min(Math.max(8, tip.x - w / 2), window.innerWidth - w - 8)
    const top = tip.y + 6 + h > window.innerHeight - 8 ? tip.y - h - 30 : tip.y + 6
    setPos({ left, top })
  }, [tip])
  if (!tip) return null
  return <div ref={box} className="tooltip" role="tooltip" style={pos}>{tip.text}</div>
}
