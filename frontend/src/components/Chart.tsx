import * as echarts from 'echarts'
import { useEffect, useRef, useState } from 'react'

/** Reads the live CSS tokens so charts follow light/dark mode. */
export function useTheme() {
  const read = () => {
    const s = getComputedStyle(document.documentElement)
    const v = (n: string) => s.getPropertyValue(n).trim()
    return {
      ink: v('--ink'), ink2: v('--ink-2'), ink3: v('--ink-3'), rule: v('--rule'),
      surface: v('--surface'), accent: v('--accent'), bench: v('--bench'), pos: v('--pos'),
      neg: v('--neg'), dark: matchMedia('(prefers-color-scheme: dark)').matches &&
        document.documentElement.dataset.theme !== 'light' || document.documentElement.dataset.theme === 'dark',
    }
  }
  const [t, setT] = useState(read)
  useEffect(() => {
    const mq = matchMedia('(prefers-color-scheme: dark)')
    const on = () => setT(read())
    mq.addEventListener('change', on)
    const mo = new MutationObserver(on)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => { mq.removeEventListener('change', on); mo.disconnect() }
  }, [])
  return t
}
export type Theme = ReturnType<typeof useTheme>

// Categorical order from the validated reference palette (light / dark steps).
export const SERIES_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
export const SERIES_DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']

export function baseOption(t: Theme): echarts.EChartsOption {
  return {
    animation: false,
    textStyle: { fontFamily: 'IBM Plex Sans, system-ui, sans-serif', color: t.ink2, fontSize: 12 },
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis', backgroundColor: t.surface, borderColor: t.rule,
      textStyle: { color: t.ink, fontSize: 12 }, axisPointer: { type: 'line', lineStyle: { color: t.ink3 } },
    },
  }
}

export function axisStyle(t: Theme) {
  return {
    axisLine: { lineStyle: { color: t.rule } },
    axisTick: { show: false },
    axisLabel: { color: t.ink3, fontSize: 11 },
    splitLine: { lineStyle: { color: t.rule, type: 'dashed' as const } },
  }
}

export function Chart({ option, className = 'chart', onClick }: {
  option: any; className?: string; onClick?: (p: any) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const inst = useRef<echarts.ECharts | null>(null)
  useEffect(() => {
    if (!ref.current) return
    inst.current = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    const ro = new ResizeObserver(() => inst.current?.resize())
    ro.observe(ref.current)
    return () => { ro.disconnect(); inst.current?.dispose(); inst.current = null }
  }, [])
  useEffect(() => { inst.current?.setOption(option, true) }, [option])
  useEffect(() => {
    if (!onClick || !inst.current) return
    inst.current.on('click', onClick)
    return () => { inst.current?.off('click', onClick) }
  }, [onClick])
  return <div ref={ref} className={className} role="img" />
}
