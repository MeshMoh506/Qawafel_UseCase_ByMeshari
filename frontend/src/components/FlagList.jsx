import { useState } from 'react'
import { reopenFlag, resolveFlag } from '../api.js'
import { sar } from '../format.js'

function Resolve({ flag, onDone }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const [by, setBy] = useState('')
  const [err, setErr] = useState('')
  if (flag.resolved) {
    return (
      <p className="resolved">
        Resolved by {flag.resolved.by}: {flag.resolved.note}{' '}
        <button className="link" onClick={async () => { await reopenFlag(flag.id); onDone() }}>Reopen</button>
      </p>
    )
  }
  if (!open) return <button className="link" onClick={() => setOpen(true)}>Resolve with a note</button>
  return (
    <form
      className="resolve"
      onSubmit={async (e) => {
        e.preventDefault()
        try { await resolveFlag(flag.id, note, by); onDone() } catch (x) { setErr(x.message) }
      }}
    >
      <label>What was checked, and what was decided?
        <textarea rows="2" value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <label>Your name
        <input value={by} onChange={(e) => setBy(e.target.value)} placeholder="Analyst" />
      </label>
      {err && <p className="err">{err}</p>}
      <div><button className="btn" type="submit">Save</button> <button type="button" className="link" onClick={() => setOpen(false)}>Cancel</button></div>
    </form>
  )
}

const GROUPS = [
  { key: 'blocking', title: 'Blocking', help: 'These stop the package from being sent. An analyst resolves each one with a written note.' },
  { key: 'warning', title: 'Warnings', help: 'These do not stop sending, but the reviewer should know about them.' },
  { key: 'note', title: 'Notes', help: 'Read correctly or left out of the figures. For information.' },
]

export default function FlagList({ flags, onChange }) {
  return (
    <div>
      {GROUPS.map((g) => {
        const items = flags.filter((f) => f.severity === g.key)
        if (!items.length) return null
        const open = items.filter((f) => !f.resolved).length
        return (
          <div key={g.key} className="flaggroup">
            <h3>{g.title} <span className="count">{g.key === 'blocking' ? `${open} open of ${items.length}` : items.length}</span></h3>
            <p className="muted">{g.help}</p>
            <ul className="flags">
              {items.map((f) => (
                <li key={f.id} className={f.resolved ? 'done' : ''}>
                  <div className="flaghead">
                    <span className={`sev ${f.severity}`}>{f.severity === 'note' ? 'Note' : f.severity === 'warning' ? 'Warning' : 'Blocking'}</span>
                    <strong>{f.title}</strong>
                    {f.amount ? <span className="amt">SAR {sar(f.amount)}</span> : null}
                  </div>
                  <p>{f.message}</p>
                  <div className="flagact">
                    <a href={`#/figure/${encodeURIComponent('flag:' + f.id)}`}>View the rows</a>
                    {f.severity === 'blocking' && <Resolve flag={f} onDone={onChange} />}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}
