import { useEffect, useState } from 'react'
import { getMethod } from '../api.js'
import { pct } from '../format.js'

const NAMES = { reference: 'Invoice number in the bank text', amount: 'Same customer, same amount', sum: 'Several invoices add up', split: 'Two deposits pay one invoice', overpayment: 'Deposit a little too high', amount_only: 'Amount only (name not recognised)' }

export default function Method() {
  const [m, setM] = useState(null)
  useEffect(() => { getMethod().then((r) => setM(r.evaluation)) }, [])
  return (
    <div className="page">
      <h1>How this was checked</h1>
      <p className="how">
        Everything on the summary is plain arithmetic on two files, with no guessing by a language model, so the same files always give the same numbers.
        This page shows how the rules did on the sample data, where the answer is known. A real customer would not come with an answer key.
      </p>

      <section>
        <h2>What the system does</h2>
        <ol className="steps">
          <li><strong>Read the invoices.</strong> Dates written as text or with Arabic-Indic digits, and amounts stored as text, are repaired and noted. Nothing is thrown away.</li>
          <li><strong>Read the statement.</strong> Each line keeps its page and line number. A page with no readable text is reported, never guessed at.</li>
          <li><strong>Merge customers.</strong> The same customer in Arabic, in English, with “Co.” or with extra spaces is one customer, joined by VAT number.</li>
          <li><strong>Match deposits to invoices</strong>, from the most certain evidence to the least: the invoice number in the bank text, then the same amount, then several invoices that add up, then two deposits for one invoice. Each match records how it was made and how sure we are.</li>
          <li><strong>Raise issues.</strong> Duplicates, an unreadable page, a balance that does not add up and money going in a circle block sending. Smaller problems are warnings.</li>
          <li><strong>Work out the figures</strong> from the matched rows only, so every number opens to the rows behind it.</li>
        </ol>
      </section>

      {m && (
        <>
          <section>
            <h2>Matching accuracy on the sample data</h2>
            <p>
              Of <strong>{m.matching.pairs_found}</strong> invoice-to-deposit matches made, <strong>{pct(m.matching.precision, 1)}</strong> are right.
              Of the <strong>{m.matching.pairs_on_readable_pages}</strong> correct matches that exist on readable pages, <strong>{pct(m.matching.recall, 1)}</strong> were found.
              Another {m.matching.not_readable} correct matches are on the page that cannot be read.
            </p>
            <table className="plain">
              <thead><tr><th>How the match was made</th><th>Confidence</th><th className="num">Made</th><th className="num">Correct</th></tr></thead>
              <tbody>
                {m.matching.by_method.map((r) => (
                  <tr key={r.method + r.confidence}><td>{NAMES[r.method]}</td><td>{r.confidence}</td><td className="num">{r.found}</td><td className="num">{r.correct}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="muted">The guesses about overpayments are marked low and sent to a person. Only high and medium matches are used without a check.</p>
          </section>

          <section>
            <h2>Planted problems found</h2>
            <table className="plain">
              <thead><tr><th>Problem put into the data</th><th className="num">Planted</th><th className="num">Found</th><th className="num">Extra</th></tr></thead>
              <tbody>
                {m.flags.map((c) => (
                  <tr key={c.name}><td>{c.name}{c.note && <span className="muted"> — {c.note}</span>}</td><td className="num">{c.planted}</td><td className="num">{c.found}</td><td className="num">{c.extra}</td></tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}

      <section>
        <h2>Assumptions</h2>
        <ul className="plainlist">
          <li>One business, one bank account, one currency (SAR), 12 months.</li>
          <li>A missing due date means 30 days after the invoice date.</li>
          <li>Revenue is the net amount, excluding VAT. Customer payments include VAT, as the bank sees them.</li>
          <li>A match is made only if the deposit date is on or after the invoice date, and the amount agrees within SAR 5 (bank fees and rounding).</li>
          <li>A credit note lowers what the customer is expected to pay for the invoice it names.</li>
          <li>An invoice that is paid by money that goes straight back to the same name is left out of confirmed revenue.</li>
        </ul>
      </section>

      <section>
        <h2>What is not built</h2>
        <ul className="plainlist">
          <li>Uploading files, editing a match by hand, freezing and sending a version, and the bank’s answer. These are written as requirements in the spec.</li>
          <li>Reading a scanned page (OCR). The system reports the page as unreadable and shows how much money moved through it.</li>
          <li>Flag resolutions are kept in memory and reset when the server restarts.</li>
        </ul>
      </section>
    </div>
  )
}
