import { sql as sqlLanguage, SQLite } from '@codemirror/lang-sql';
import CodeMirror, { type ReactCodeMirrorRef } from '@uiw/react-codemirror';
import { forwardRef, useEffect, useMemo, useState } from 'react';
import { api, type TableSchema, type Validation } from '../api';

interface Props {
  value: string;
  baseSql: string;
  tables: TableSchema[];
  theme: 'light' | 'dark';
  running: boolean;
  executing: boolean;
  onChange: (sql: string) => void;
  onRun: () => void;
}

type Check = { state: 'idle' | 'checking' } | { state: 'done'; result: Validation } | { state: 'offline' };

export const SqlPanel = forwardRef<ReactCodeMirrorRef, Props>(function SqlPanel(
  { value, baseSql, tables, theme, running, executing, onChange, onRun }, ref) {
  const check = useValidation(value, running);
  const edited = baseSql !== '' && value.trim() !== baseSql.trim();
  const unsafe = check.state === 'done' && !check.result.valid && !check.result.retryable;

  const extensions = useMemo(() => [sqlLanguage({
    dialect: SQLite,
    schema: Object.fromEntries(tables.map((t) => [t.name, t.columns.map((c) => c.name)])),
    upperCaseKeywords: true,
  })], [tables]);

  return (
    <section className="card" aria-label="SQL">
      <div className="card-head">
        <h2>SQL</h2>
        {edited && <span className="pill accent">Edited</span>}
        <span className="spacer" />
        <ValidationPill check={check} empty={!value.trim()} />
        {edited && <button className="btn small ghost" onClick={() => onChange(baseSql)}>Reset to generated</button>}
        <button className="btn primary small" onClick={onRun}
                disabled={!value.trim() || running || executing || unsafe}
                title="Run this SQL (Ctrl+Shift+Enter)">
          {executing ? 'Running…' : '▶ Run'}
        </button>
      </div>
      <div className="editor">
        <CodeMirror ref={ref} value={value} onChange={onChange} extensions={extensions}
                    theme={theme} minHeight="96px" maxHeight="320px" readOnly={running}
                    placeholder="Generated SQL appears here. You can also write your own."
                    basicSetup={{ foldGutter: false, highlightActiveLine: false }} aria-label="SQL editor" />
      </div>
      {check.state === 'done' && !check.result.valid && (
        <div className={`banner ${check.result.retryable ? 'warn' : 'bad'}`} style={{ margin: 12 }} role="alert">
          {check.result.retryable ? <strong>{check.result.error_type}: </strong>
            : <strong>⛔ Blocked for safety: </strong>}
          {check.result.error}
        </div>
      )}
    </section>
  );
});

function ValidationPill({ check, empty }: { check: Check; empty: boolean }) {
  if (empty || check.state === 'idle') return null;
  if (check.state === 'checking') return <span className="pill">Checking…</span>;
  if (check.state !== 'done') return <span className="pill">Validator unavailable</span>;
  const { result } = check;
  if (result.valid) return <span className="pill ok"><span aria-hidden>✓</span><span>Valid</span></span>;
  if (!result.retryable) return <span className="pill bad"><span aria-hidden>⛔</span><span>Unsafe</span></span>;
  return <span className="pill warn"><span aria-hidden>✗</span><span>{result.error_type}</span></span>;
}

/** Validate the editor contents on the server, debounced, cancelling stale requests. */
function useValidation(sql: string, paused: boolean): Check {
  const [check, setCheck] = useState<Check>({ state: 'idle' });
  useEffect(() => {
    if (paused || !sql.trim()) { setCheck({ state: 'idle' }); return; }
    const controller = new AbortController();
    setCheck({ state: 'checking' });
    const timer = setTimeout(() => {
      api.validate(sql, controller.signal)
        .then((result) => setCheck({ state: 'done', result }))
        .catch((e) => { if (e.name !== 'AbortError') setCheck({ state: 'offline' }); });
    }, 400);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [sql, paused]);
  return check;
}
