const BASE = '/v1/package-versions/demo'

async function get(path) {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

export const getSummary = () => get(`${BASE}/summary`)
export const getFigure = (key) => get(`${BASE}/figures/${key}`)
export const getMethod = () => get(`${BASE}/method`)

export async function resolveFlag(id, note, by) {
  const r = await fetch(`/v1/flags/${id}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note, by }),
  })
  if (!r.ok) throw new Error('A note is required to resolve an issue.')
  return r.json()
}

export const reopenFlag = (id) => fetch(`/v1/flags/${id}/reopen`, { method: 'POST' }).then((r) => r.json())
