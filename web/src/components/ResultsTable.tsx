import { useMemo, useState } from 'react';
import type { QueryRecord } from '../api';

const PAGE_SIZE = 50;

interface Props {
  record: QueryRecord | null;
  running: boolean;
  maxRows: number | null;
}

export function ResultsTable({ record, running, maxRows }: Props) {
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null);
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const result = record?.result ?? null;

  const numeric = useMemo(() => result?.columns.map((_, i) =>
    result.rows.length > 0 && result.rows.every((r) => r[i] === null || typeof r[i] === 'number')) ?? [], [result]);

  const rows = useMemo(() => {
    if (!result) return [];
    const needle = filter.trim().toLowerCase();
    let rows = needle ? result.rows.filter((r) => r.some((v) => String(v ?? '').toLowerCase().includes(needle))) : result.rows;
    if (sort) rows = [...rows].sort((a, b) => compare(a[sort.col], b[sort.col]) * sort.dir);
    return rows;
  }, [result, filter, sort]);

  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const visible = rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  const head = (
    <div className="card-head">
      <h2>Results</h2>
      {record && <span className="muted" style={{ fontSize: 13 }}>
        {result ? `${result.rows.length.toLocaleString()} row${result.rows.length === 1 ? '' : 's'} · ` : ''}
        {record.latency.toFixed(2)}s
      </span>}
      <span className="spacer" />
      {result && result.rows.length > 0 && <>
        <input type="search" placeholder="Filter rows…" value={filter} aria-label="Filter rows"
               onChange={(e) => { setFilter(e.target.value); setPage(0); }} style={{ width: 180 }} />
        <button className="btn small" onClick={() => downloadCsv(result.columns, rows, record!.id)}>⤓ CSV</button>
      </>}
    </div>
  );

  if (running) {
    return <section className="card" aria-busy="true">{head}{[0, 1, 2].map((i) => <div key={i} className="skeleton" />)}</section>;
  }
  if (!record) {
    return <section className="card">{head}<p className="empty">Ask a question or run SQL to see results.</p></section>;
  }
  if (!result) {
    const unsafe = record.error_type === 'unsafe' || record.error_type === 'authorization';
    return (
      <section className="card">{head}
        <div className={`banner ${unsafe ? 'bad' : record.status === 'validation_failed' ? 'warn' : 'bad'}`} style={{ margin: 14 }} role="alert">
          <strong>{unsafe ? '⛔ Query blocked for safety. ' : record.status === 'validation_failed'
            ? 'No valid SQL could be produced. ' : 'Query failed. '}</strong>
          {record.error}
          {record.status === 'validation_failed' && !unsafe && <div style={{ marginTop: 4 }}>Edit the SQL above and run it again.</div>}
        </div>
      </section>
    );
  }

  return (
    <section className="card" aria-label="Results">
      {head}
      {result.truncated && (
        <div className="banner warn" style={{ margin: '10px 14px 0' }}>
          Showing the first {maxRows?.toLocaleString() ?? result.rows.length} rows; the row limit was reached. Add a LIMIT or filter to narrow it.
        </div>
      )}
      {result.rows.length === 0 ? <p className="empty">The query ran successfully and returned 0 rows.</p> : (
        <>
          <div className="table-wrap">
            <table className="results">
              <thead>
                <tr>{result.columns.map((col, i) => (
                  <th key={i} className={numeric[i] ? 'num' : ''}
                      aria-sort={sort?.col === i ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                    <button onClick={() => setSort(sort?.col === i ? (sort.dir === 1 ? { col: i, dir: -1 } : null) : { col: i, dir: 1 })}>
                      {col}<span aria-hidden className="muted">{sort?.col === i ? (sort.dir === 1 ? '▲' : '▼') : ''}</span>
                    </button>
                  </th>))}
                </tr>
              </thead>
              <tbody>
                {visible.map((row, r) => (
                  <tr key={r}>{row.map((v, i) => (
                    <td key={i} className={numeric[i] ? 'num' : ''}>
                      {v === null ? <span className="null">null</span> : formatCell(v)}
                    </td>))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(pages > 1 || filter) && (
            <div className="pager">
              <span className="muted">{filter && `${rows.length.toLocaleString()} matching · `}Page {current + 1} of {pages}</span>
              <span className="spacer" />
              <button className="btn small" disabled={current === 0} onClick={() => setPage(current - 1)}>Previous</button>
              <button className="btn small" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>Next</button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function compare(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

function formatCell(value: unknown): string {
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return String(value);
}

export function toCsv(columns: string[], rows: unknown[][]): string {
  const cell = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [columns, ...rows].map((r) => r.map(cell).join(',')).join('\r\n');
}

function downloadCsv(columns: string[], rows: unknown[][], id: string) {
  const url = URL.createObjectURL(new Blob([toCsv(columns, rows)], { type: 'text/csv' }));
  const link = Object.assign(document.createElement('a'), { href: url, download: `query-${id.slice(0, 8)}.csv` });
  link.click();
  URL.revokeObjectURL(url);
}
