import { useEffect, useState } from 'react'
import { getFigure } from '../api.js'
import DataTable from '../components/DataTable.jsx'

export default function Figure({ figKey }) {
  const [f, setF] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    setF(null); setErr('')
    getFigure(figKey).then(setF).catch((e) => setErr(e.message))
  }, [figKey])
  if (err) return <div className="page"><p><a href="#/">← Back to the summary</a></p><p className="err">Could not load these rows: {err}</p></div>
  if (!f) return <div className="page"><p className="muted">Loading…</p></div>
  return (
    <div className="page">
      <p><a href="#/">← Back to the summary</a></p>
      <h1>{f.title}</h1>
      <p className="how">{f.how}</p>
      {f.tables.map((t) => <DataTable key={t.name} table={t} />)}
    </div>
  )
}
