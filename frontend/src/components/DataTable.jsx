import { useMemo, useState } from "react";
import { day, sar } from "../format.js";

const INV_COLS = [
  { key: "no", label: "Invoice" },
  { key: "date", label: "Date", fmt: day },
  { key: "customer", label: "Customer", auto: true },
  { key: "net", label: "Net (SAR)", num: true },
  { key: "total", label: "Total (SAR)", num: true },
  { key: "status", label: "Status" },
  { key: "days_to_pay", label: "Days to pay", num: true, plain: true },
  { key: "source", label: "Source" },
];
const TXN_COLS = [
  { key: "date", label: "Date", fmt: day },
  { key: "description", label: "Description", auto: true },
  { key: "debit", label: "Out (SAR)", num: true, blankZero: true },
  { key: "credit", label: "In (SAR)", num: true, blankZero: true },
  { key: "state", label: "Match" },
  { key: "source", label: "Source" },
];
const PAGE_COLS = [
  { key: "page", label: "Page", plain: true },
  { key: "source", label: "Source" },
];

function cell(col, row) {
  const v = row[col.key];
  if (v == null || v === "") return "";
  if (col.blankZero && v === 0) return "";
  if (col.num && !col.plain) return sar(v, 2);
  if (col.fmt) return col.fmt(v);
  return v;
}

function Detail({ row }) {
  if (row.kind === "invoice") {
    return (
      <div className="detail">
        {row.paid_by.length === 0 &&
          !String(row.status).startsWith("not used") && (
            <p>No payment found for this invoice.</p>
          )}
        {row.paid_by.map((p) => (
          <p key={p.txn + p.amount}>
            Paid SAR {sar(p.amount, 2)} by bank line {p.txn} ({p.how},{" "}
            {p.confidence} confidence)
          </p>
        ))}
        {row.type === "Invoice" && (
          <p>
            Due {day(row.due)}
            {row.due_assumed ? " (assumed: the file has no due date)" : ""}
            {row.days_overdue
              ? `, ${row.days_overdue} days overdue at the end of the period`
              : ""}
          </p>
        )}
        {row.name_in_file !== row.customer && (
          <p>
            Written in the file as “<span dir="auto">{row.name_in_file}</span>”
          </p>
        )}
        {row.notes.map((n) => (
          <p key={n}>Note: {n}</p>
        ))}
      </div>
    );
  }
  if (row.kind === "transaction") {
    return (
      <div className="detail">
        <p>Balance printed on the statement: SAR {sar(row.balance, 2)}</p>
        {row.customer && (
          <p>
            Customer read from the text: <span dir="auto">{row.customer}</span>
          </p>
        )}
        {row.applied_to.length === 0 && row.state === "no invoice found" && (
          <p>No invoice in this package matches this deposit.</p>
        )}
        {row.applied_to.map((m) => (
          <p key={m.invoice + m.amount}>
            Applied SAR {sar(m.amount, 2)} to {m.invoice} ({m.how},{" "}
            {m.confidence} confidence){m.note ? `: ${m.note}` : ""}
          </p>
        ))}
      </div>
    );
  }
  return null;
}

export default function DataTable({ table }) {
  const cols =
    table.kind === "invoice"
      ? INV_COLS
      : table.kind === "transaction"
        ? TXN_COLS
        : PAGE_COLS;
  const [q, setQ] = useState("");
  const [sort, setSort] = useState(null);
  const [open, setOpen] = useState(null);
  const [limit, setLimit] = useState(100);
  const rows = useMemo(() => {
    let r = table.rows;
    if (q.trim()) {
      const s = q.trim().toLowerCase();
      r = r.filter((x) => JSON.stringify(x).toLowerCase().includes(s));
    }
    if (sort) {
      const { key, dir } = sort;
      r = [...r].sort(
        (a, b) => ((a[key] ?? "") > (b[key] ?? "") ? 1 : -1) * dir,
      );
    }
    return r;
  }, [table.rows, q, sort]);
  const total = (key) => rows.reduce((s, r) => s + (r[key] || 0), 0);
  const csv = () => {
    const head = cols.map((c) => c.label).join(",");
    const body = rows
      .map((r) =>
        cols
          .map(
            (c) =>
              `"${String(c.num && !c.plain ? (r[c.key] ?? "") / 100 : (r[c.key] ?? "")).replace(/"/g, '""')}"`,
          )
          .join(","),
      )
      .join("\n");
    const url = URL.createObjectURL(
      new Blob([head + "\n" + body], { type: "text/csv" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `${table.name.toLowerCase().replace(/\s+/g, "-")}.csv`;
    a.click();
  };
  return (
    <section className="tablewrap">
      <div className="tablehead">
        <h2>
          {table.name} <span className="count">{rows.length}</span>
        </h2>
        {table.kind !== "pages" && (
          <div className="tools">
            <input
              type="search"
              placeholder="Search these rows"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button className="link" onClick={csv}>
              Download CSV
            </button>
          </div>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="muted">No rows.</p>
      ) : (
        <table className="data">
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c.key} className={c.num ? "num" : ""}>
                  <button
                    className="th"
                    onClick={() =>
                      setSort(
                        sort && sort.key === c.key
                          ? { key: c.key, dir: -sort.dir }
                          : { key: c.key, dir: 1 },
                      )
                    }
                  >
                    {c.label}
                    {sort && sort.key === c.key
                      ? sort.dir === 1
                        ? " ↑"
                        : " ↓"
                      : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((r, i) => {
              const id = r.id || r.page || i;
              return [
                <tr
                  key={id}
                  className={open === id ? "open" : ""}
                  onClick={() => setOpen(open === id ? null : id)}
                >
                  {cols.map((c) => (
                    <td
                      key={c.key}
                      className={c.num ? "num" : ""}
                      dir={c.auto ? "auto" : undefined}
                    >
                      {cell(c, r)}
                    </td>
                  ))}
                </tr>,
                open === id && table.kind !== "pages" && (
                  <tr key={id + "d"} className="detailrow">
                    <td colSpan={cols.length}>
                      <Detail row={r} />
                    </td>
                  </tr>
                ),
              ];
            })}
          </tbody>
          {table.kind === "invoice" && (
            <tfoot>
              <tr>
                <td colSpan={3}>Total of the rows shown</td>
                <td className="num">{sar(total("net"), 2)}</td>
                <td className="num">{sar(total("total"), 2)}</td>
                <td colSpan={3}></td>
              </tr>
            </tfoot>
          )}
          {table.kind === "transaction" && (
            <tfoot>
              <tr>
                <td colSpan={2}>Total of the rows shown</td>
                <td className="num">{sar(total("debit"), 2)}</td>
                <td className="num">{sar(total("credit"), 2)}</td>
                <td colSpan={2}></td>
              </tr>
            </tfoot>
          )}
        </table>
      )}
      {rows.length > limit && (
        <button className="link" onClick={() => setLimit(limit + 200)}>
          Show more ({rows.length - limit} left)
        </button>
      )}
    </section>
  );
}
