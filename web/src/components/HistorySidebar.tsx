import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type HistoryItem } from '../api';

type Filter = 'all' | 'starred' | 'failed';

interface Props {
  activeId: string | undefined;
  onDeleted: (id: string) => void;
}

export function HistorySidebar({ activeId, onDeleted }: Props) {
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const client = useQueryClient();

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['history', debounced, filter],
    queryFn: () => api.history({
      search: debounced,
      status: filter === 'failed' ? 'failed' : undefined,
      starred: filter === 'starred' ? true : undefined,
    }),
  });
  const refresh = () => client.invalidateQueries({ queryKey: ['history'] });
  const star = useMutation({ mutationFn: (item: HistoryItem) => api.star(item.id, !item.starred), onSuccess: refresh });
  const remove = useMutation({
    mutationFn: (id: string) => api.remove(id),
    onSuccess: (_, id) => { refresh(); onDeleted(id); },
  });

  const groups = groupByDay(data?.items ?? []);

  const renderItem = (item: HistoryItem, children: HistoryItem[] = []) => (
    <div key={item.id}>
      <div className={`history-item ${item.id === activeId ? 'active' : ''}`}>
        <span className={`dot ${item.status}`} role="img" aria-label={item.status.replace('_', ' ')} />
        <Link to={`/q/${item.id}`} className="label" title={item.question || item.final_sql || ''}
              aria-current={item.id === activeId ? 'page' : undefined}>
          {item.kind === 'manual' && <span className="muted" aria-label="edited SQL">✎ </span>}
          {item.question || item.final_sql}
        </Link>
        <span className="actions">
          <button className="icon-btn" aria-label="Delete" title="Delete"
                  onClick={() => { if (confirm('Delete this query from history?')) remove.mutate(item.id); }}>
            🗑
          </button>
        </span>
        <button className={`icon-btn star ${item.starred ? 'on' : ''}`} aria-pressed={item.starred}
                aria-label={item.starred ? 'Unstar' : 'Star'} onClick={() => star.mutate(item)}>
          {item.starred ? '★' : '☆'}
        </button>
      </div>
      {children.length > 0 && <div className="history-children">{children.map((c) => renderItem(c))}</div>}
    </div>
  );

  return (
    <nav className="history" aria-label="Query history">
      <h2>History</h2>
      <input type="search" placeholder="Search questions or SQL…" value={search}
             onChange={(e) => setSearch(e.target.value)} aria-label="Search history" />
      <div className="filters" role="group" aria-label="Filter history">
        {(['all', 'starred', 'failed'] as Filter[]).map((f) => (
          <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {f[0].toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>
      {isLoading && <div className="skeleton" />}
      {isError && <p className="muted">Could not load history.</p>}
      {data && data.items.length === 0 && (
        <p className="muted" style={{ fontSize: 13 }}>
          {debounced || filter !== 'all' ? 'No matching queries.' : 'Questions you ask will appear here.'}
        </p>
      )}
      {groups.map(([day, items]) => (
        <section key={day} className="history-group">
          <h2 style={{ marginBottom: 4 }}>{day}</h2>
          {nest(items).map(([item, children]) => renderItem(item, children))}
        </section>
      ))}
    </nav>
  );
}

function groupByDay(items: HistoryItem[]): [string, HistoryItem[]][] {
  const today = new Date().toDateString();
  const yesterday = new Date(Date.now() - 86_400_000).toDateString();
  const groups = new Map<string, HistoryItem[]>();
  for (const item of items) {
    const date = new Date(item.created_at);
    const key = date.toDateString() === today ? 'Today'
      : date.toDateString() === yesterday ? 'Yesterday'
      : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return [...groups];
}

/** Put manual re-runs under the agent run they came from, when both are on screen. */
function nest(items: HistoryItem[]): [HistoryItem, HistoryItem[]][] {
  const ids = new Set(items.map((i) => i.id));
  const children = new Map<string, HistoryItem[]>();
  for (const item of items) {
    if (item.parent_id && ids.has(item.parent_id)) {
      children.set(item.parent_id, [...(children.get(item.parent_id) ?? []), item]);
    }
  }
  return items
    .filter((i) => !(i.parent_id && ids.has(i.parent_id)))
    .map((i) => [i, children.get(i.id) ?? []]);
}
