import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ReactCodeMirrorRef } from '@uiw/react-codemirror';
import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, askStream } from './api';
import { HistorySidebar } from './components/HistorySidebar';
import { QuestionInput } from './components/QuestionInput';
import { ResultsTable } from './components/ResultsTable';
import { SchemaDrawer } from './components/SchemaDrawer';
import { SettingsDialog } from './components/SettingsDialog';
import { SetupScreen } from './components/SetupScreen';
import { SqlPanel } from './components/SqlPanel';
import { TopBar } from './components/TopBar';
import { TracePanel } from './components/TracePanel';
import { initialState, reducer, rootId } from './workspace';

type MobileTab = 'history' | 'ask' | 'trace';

export function App() {
  const { id } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [state, dispatch] = useReducer(reducer, initialState);
  const [theme, setTheme] = useTheme();
  const [panes, setPanes] = useState({ left: true, right: true });
  const [mobileTab, setMobileTab] = useState<MobileTab>('ask');
  const [dialog, setDialog] = useState<'settings' | 'schema' | null>(null);
  const abort = useRef<AbortController | null>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const editorRef = useRef<ReactCodeMirrorRef>(null);

  const health = useQuery({ queryKey: ['health'], queryFn: api.health });
  const ready = !!health.data?.ready;
  const schema = useQuery({ queryKey: ['schema'], queryFn: api.schema, enabled: ready });
  const routed = useQuery({ queryKey: ['record', id], queryFn: () => api.record(id!), enabled: !!id });

  // The URL is the source of truth for which saved query is on screen.
  useEffect(() => {
    if (state.running) return;
    if (id && routed.data && state.record?.id !== id) dispatch({ type: 'load', record: routed.data });
    if (!id && state.record) dispatch({ type: 'reset' });
  }, [id, routed.data, state.record, state.running]);

  const showRecord = useCallback((record: { id: string }) => {
    client.setQueryData(['record', record.id], record);
    client.invalidateQueries({ queryKey: ['history'] });
    navigate(`/q/${record.id}`);
  }, [client, navigate]);

  const ask = useCallback(async (question: string) => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    navigate('/');
    dispatch({ type: 'start', question });
    setMobileTab('ask');
    try {
      for await (const event of askStream(question, controller.signal)) {
        dispatch({ type: 'event', event });
        if (event.stage === 'done') showRecord(event.data);
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') dispatch({ type: 'cancelled' });
      else dispatch({ type: 'failed', error: (e as Error).message });
    }
  }, [navigate, showRecord]);

  const execute = useMutation({
    mutationFn: () => api.execute(state.sql, state.question, rootId(state.record)),
    onSuccess: showRecord,
  });
  const runSql = useCallback(() => {
    if (state.sql.trim() && !state.running && !execute.isPending) execute.mutate();
  }, [state.sql, state.running, execute]);

  const insert = (text: string) => {
    const view = editorRef.current?.view;
    if (view && !state.running) {
      view.dispatch(view.state.replaceSelection(text));
      view.focus();
    } else {
      dispatch({ type: 'sql', sql: state.sql ? `${state.sql} ${text}` : text });
    }
    setDialog(null);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement).closest('input, textarea, select, [contenteditable="true"]');
      if (e.key === 'Enter' && e.shiftKey && (e.ctrlKey || e.metaKey)) { e.preventDefault(); runSql(); return; }
      if (typing || dialog || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === '/') { e.preventDefault(); questionRef.current?.focus(); }
      if (e.key === '[') setPanes((p) => ({ ...p, left: !p.left }));
      if (e.key === ']') setPanes((p) => ({ ...p, right: !p.right }));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [runSql, dialog]);

  const newQuery = () => {
    abort.current?.abort();
    navigate('/');
    dispatch({ type: 'reset' });
    setMobileTab('ask');
    setTimeout(() => questionRef.current?.focus());
  };

  const paneClass = (name: MobileTab, visible: boolean, extra: string) =>
    `pane ${extra} ${visible ? '' : 'hidden'} ${mobileTab === name ? 'mobile-active' : ''}`;

  return (
    <div className="app">
      <TopBar health={health.data} theme={theme} onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              onOpenSchema={() => setDialog('schema')} onOpenSettings={() => setDialog('settings')} onNew={newQuery}
              panes={panes} onTogglePane={(side) => setPanes((p) => ({ ...p, [side]: !p[side] }))} />

      {health.isError && (
        <main className="setup"><div className="banner bad" role="alert">
          Cannot reach the server. Make sure it is running, then reload this page.
        </div></main>
      )}
      {health.data && !ready && <SetupScreen health={health.data} onOpenSettings={() => setDialog('settings')} />}

      {ready && health.data && <>
        <div className="mobile-tabs" role="tablist">
          {(['history', 'ask', 'trace'] as MobileTab[]).map((tab) => (
            <button key={tab} role="tab" aria-selected={mobileTab === tab} onClick={() => setMobileTab(tab)}>
              {tab[0].toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        <div className="panes" style={{
          ['--left' as string]: panes.left ? '260px' : '0px', ['--right' as string]: panes.right ? '340px' : '0px',
        }}>
          <div className={paneClass('history', panes.left, 'side left')}>
            <HistorySidebar activeId={id} onDeleted={(deleted) => deleted === id && newQuery()} />
          </div>
          <main className={paneClass('ask', true, '')}>
            <div className="workspace">
              <QuestionInput ref={questionRef} value={state.question} running={state.running}
                             onChange={(q) => dispatch({ type: 'question', question: q })} onAsk={ask}
                             onCancel={() => abort.current?.abort()} />
              {state.error && <div className="banner bad" role="alert">{state.error}</div>}
              {execute.error && <div className="banner bad" role="alert">{execute.error.message}</div>}
              {routed.isError && <div className="banner bad" role="alert">That query is no longer in history.</div>}
              <SqlPanel ref={editorRef} value={state.sql} baseSql={state.baseSql} tables={schema.data?.tables ?? []}
                        theme={theme} running={state.running} executing={execute.isPending}
                        onChange={(sql) => dispatch({ type: 'sql', sql })} onRun={runSql} />
              <ResultsTable key={state.record?.id} record={state.record} running={state.running || execute.isPending}
                            maxRows={health.data.max_rows} />
            </div>
          </main>
          <div className={paneClass('trace', panes.right, 'side right')}>
            <TracePanel trace={state.trace} record={state.record} running={state.running} />
          </div>
        </div>
      </>}

      {dialog === 'settings' && <SettingsDialog health={health.data} onClose={() => setDialog(null)} />}
      {dialog === 'schema' && schema.data && (
        <SchemaDrawer tables={schema.data.tables} onInsert={insert} onClose={() => setDialog(null)} />
      )}
    </div>
  );
}

function useTheme(): ['light' | 'dark', (theme: 'light' | 'dark') => void] {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      const saved = localStorage.getItem('theme');
      if (saved === 'light' || saved === 'dark') return saved;
    } catch { /* storage unavailable */ }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('theme', theme); } catch { /* storage unavailable */ }
  }, [theme]);
  return [theme, setTheme];
}
