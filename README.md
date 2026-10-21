# Financing package review (Qawafel assessment, Task 3)

A small working prototype for the scenario in the brief: an SME wholesaler uploads 12 months of invoices (Excel) and bank statements (PDF), and Qawafel turns them into a package a bank can review.

**The question it answers:** *can this business repay a working-capital loan, and what in the files should a person check before the bank sees them?*

Invoices are claims. The bank statement is evidence. The prototype matches the two, and every figure it shows opens to the invoices and bank lines behind it. Everything is plain arithmetic: no language model is used to produce a number, so the same files always give the same result.

All data is made up. Business: Al Noor Trading Est. (fictional food wholesaler, Riyadh). Bank: fictional.

## What you can do in it

- **Summary page.** Revenue, share confirmed by bank deposits, collection rate, days to pay, customer concentration, a monthly chart, an "invoiced to confirmed" bridge, overdue invoices, bank balances, and the issues found.
- **Click anything** to see the rows behind it: search, sort, download CSV, click a row for detail (which invoice a deposit paid, how the match was made, and how sure the system is).
- **Issues.** Blocking issues (duplicate rows, an unreadable statement page, a balance that does not add up, money going in a circle) must be resolved with a written note before the package counts as ready.
- **How this was checked** (`#/method`). Matching accuracy and planted-problem detection against the answer key.

## Run it

Needs Python 3.10+ and Node 18+.

```bash
# 1. API
cd backend
pip install -r requirements.txt
cd ../frontend && npm install && npm run build      # builds frontend/dist
cd ../backend && uvicorn app.main:app --port 8000   # open http://localhost:8000
```

Development with hot reload: run the API as above, then `cd frontend && npm run dev` and open http://localhost:5173 (Vite proxies `/v1` to port 8000).

Tests: `cd backend && pytest` (9 tests: parsing, matching, flags, API).

Docker: `docker build -t package-review . && docker run -p 8000:8000 package-review`.

## Deploy

The Dockerfile builds the React app and serves it from the same FastAPI process, so it is one service on one URL. On Render, Railway or Fly.io: create a web service from this repo, choose Docker, and it works as is (the `PORT` variable is respected). No database, no secrets.

## Where the sample data is

`data/sample/`

| File | What it is |
| --- | --- |
| `invoices_12m.xlsx` | The wholesaler's invoice export, 1 Oct 2025 to 30 Sep 2026 (862 rows, 29 customers) |
| `bank_statement_12m.pdf` | The bank statement, 28 pages, Arabic and English |
| `bank_transactions_truth.csv` | Machine-readable twin of the statement (used only to score the parser) |
| `ground_truth_matches.csv` | Which deposit really pays which invoice (used only to score the matcher) |
| `answer_key_issues.csv` | Every problem planted in the data, with its location |
| `generate_data.py` | Makes all of the above. Seeded, so it gives the same files each time: `python3 generate_data.py OUTDIR` |

The app reads only the two real inputs (the xlsx and the pdf). The other three files exist so the prototype can be graded against a known answer.

## Assumptions behind the sample data

- A food and beverage wholesaler in Riyadh with about SAR 18M of sales a year before VAT, 29 customers, and a few large customers (top five are about 42% of revenue).
- Sunday to Thursday working week. Mostly 30-day terms; hotels and caterers on 45 or 60.
- Customers pay on a spread of days around their terms, in a single payment, in several invoices at once, or in two parts. A few pay late and a few never.
- 15% VAT on every invoice. Customers pay the VAT-inclusive amount.
- Bank text is messy the way real statements are: sometimes the invoice number is in it, often only the customer name, and sometimes a name that is spelled differently from the invoice file.
- Some customers appear in several spellings (Arabic, English, "Co.", extra spaces).
- Problems put in on purpose so the prototype has something to find: repeated rows, re-issued invoices, missing invoice numbers, due dates and VAT numbers, wrong VAT, credit notes that name no invoice, an unreadable (scanned) statement page, a page with an edited balance, money that goes out and straight back in, deposits that are not sales (loans, owner money, refunds), a month with almost no customer payments, and invoices unpaid for over 90 days.

## Assumptions in the prototype

- One business, one bank account, one currency (SAR), 12 months.
- Revenue = net amount excluding VAT. Customer receipts include VAT, as the bank sees them.
- A missing due date means 30 days after the invoice date.
- A deposit can pay an invoice only on or after the invoice date, and only if the amount agrees within SAR 5.
- Matching order, from the most certain evidence to the least: invoice number in the bank text, same customer and amount, several invoices that add up, two deposits for one invoice, a slightly high deposit (low confidence), amount only (low confidence). Low-confidence matches are shown but sent to a person.
- Customers are merged by VAT number. A row without one is matched by name and flagged.

## How well it works on the sample data

- 721 matches made, 99.6% right. 96.9% of the correct matches that sit on readable pages were found.
- The weakest step is the "deposit a little too high" guess (7 of 10 right), which is why it is marked low.
- All planted problems were found. One re-issued invoice was missed, and the "unpaid over 90 days" check also lists 38 invoices that are probably paid on the unreadable page. The summary says so.

## What is not built (and where it is specified)

- File upload, hand-editing a match, freezing a version and sending it to the bank, and the bank's answer. These are in the technical spec (sections 2.1 to 2.3) and the integration plan (Task 4).
- Reading the scanned page (OCR). The prototype reports the page as unreadable and shows how much money moved through it. Guessing at it would put invented numbers in front of a bank.
- Saving flag resolutions: they are held in memory and reset when the server restarts.
- Login and roles.

## Layout

```
backend/app/   money, invoice and statement readers, matching, analysis, API
backend/tests/ pytest
frontend/src/  React app (summary, drill-down, method), no UI or chart libraries
data/sample/   the sample data and its generator
```

## AI tools used

Claude (Anthropic) helped write the code, the sample-data generator, the tests and this README, and helped draft the written spec. I ran the app and checked the numbers against the answer key myself. A first set of sample data produced by another AI tool had defects (repeated transaction ids, payments bunched on a few days, unreadable Arabic in the PDF), so it was replaced with the generator in this repo.
