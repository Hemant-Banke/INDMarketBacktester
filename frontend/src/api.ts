export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: opts.method ?? (opts.body !== undefined ? 'POST' : 'GET'),
    headers: opts.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try {
      const j = await r.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* not json */ }
    throw new Error(msg)
  }
  return r.json()
}

export type MetricInfo = { name: string; category: string; description: string; unit: string }
export type FunctionInfo = { signature: string; description: string }
export type Catalog = { metrics: MetricInfo[]; functions: FunctionInfo[] }

let catalogPromise: Promise<Catalog> | null = null
export function getCatalog(): Promise<Catalog> {
  catalogPromise ??= api<Catalog>('/metrics').catch((e) => { catalogPromise = null; throw e })
  return catalogPromise
}

export type Filter = { formula: string; enabled?: boolean }
export type Column = { name: string; formula: string }
export type Screen = {
  id?: string
  name?: string
  filters: Filter[]
  columns?: Column[]
  sort?: { by: string; desc: boolean }
  limit?: number | null
  base?: { include_sme?: boolean }
}
/** Keep ranks from..to (1 = highest `by`), re-ranked every `refresh` sessions, point-in-time. */
export type RankSlice = { by: string; from: number; to: number; refresh: number }

export type Universe = (
  | { type: 'all'; include_sme?: boolean }
  | { type: 'manual'; symbols: string[] }
  | { type: 'screen'; screen?: Screen; screen_id?: string }
) & { rank?: RankSlice }
export type SavedUniverse = { id: string; name: string; universe: Universe }
