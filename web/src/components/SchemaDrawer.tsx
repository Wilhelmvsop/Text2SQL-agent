import { useEffect, useState } from 'react';
import type { TableSchema } from '../api';

interface Props {
  tables: TableSchema[];
  onInsert: (text: string) => void;
  onClose: () => void;
}

export function SchemaDrawer({ tables, onInsert, onClose }: Props) {
  const [filter, setFilter] = useState('');
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const needle = filter.toLowerCase();
  const shown = tables.filter((t) => !needle || t.name.toLowerCase().includes(needle)
    || t.columns.some((c) => c.name.toLowerCase().includes(needle)));

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="schema-title">
        <div className="dialog-head">
          <h1 id="schema-title">Schema</h1>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div style={{ padding: '12px 18px' }}>
          <input type="search" placeholder="Find a table or column…" value={filter} autoFocus
                 onChange={(e) => setFilter(e.target.value)} aria-label="Filter schema" />
          <p className="muted" style={{ fontSize: 12, margin: '6px 0 0' }}>Click a name to insert it into the SQL editor.</p>
        </div>
        {shown.map((table) => (
          <section key={table.name} className="schema-table">
            <button className="schema-col" style={{ padding: 0 }} onClick={() => onInsert(table.name)}>
              <h3>{table.name}</h3>
            </button>
            {table.description && <p className="muted" style={{ fontSize: 12.5, margin: '0 0 6px' }}>{table.description}</p>}
            {table.columns.map((c) => {
              const fk = table.foreign_keys.find((f) => f.column === c.name);
              return (
                <button key={c.name} className="schema-col" onClick={() => onInsert(c.name)}
                        title={fk ? `References ${fk.target_table}.${fk.target_column}` : undefined}>
                  {c.primary_key && <span aria-label="primary key">🔑</span>}
                  {c.name}
                  {fk && <span className="muted">→ {fk.target_table}</span>}
                  <span className="type">{c.type}</span>
                </button>
              );
            })}
          </section>
        ))}
      </aside>
    </div>
  );
}
