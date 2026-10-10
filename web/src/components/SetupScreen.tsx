import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { api, type Health } from '../api';
import { DatabaseUpload } from './DatabaseUpload';

interface Props {
  health: Health;
  onOpenSettings: () => void;
}

/** Shown instead of the workspace until a database exists and a model is connected. */
export function SetupScreen({ health, onOpenSettings }: Props) {
  const client = useQueryClient();
  const [replacing, setReplacing] = useState(false);
  const fileName = health.db_path.split(/[\\/]/).pop();
  const create = useMutation({
    mutationFn: api.createDemoDatabase,
    onSuccess: () => client.invalidateQueries(),
  });

  return (
    <main className="setup">
      <h1>Set up Text2SQL</h1>
      <p className="muted" style={{ margin: 0 }}>
        The app turns your questions into SQL with a language model, so it needs a database and a connected model before it can be used.
      </p>
      {health.error && (
        <div className="banner bad" role="alert">
          <strong>The saved settings could not be loaded.</strong>
          <div className="mono" style={{ marginTop: 4 }}>{health.error}</div>
        </div>
      )}
      <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Step n={1} done={health.database_exists} title="Database">
          {health.database_exists && !replacing ? <>
            Using <code title={health.db_path}>{fileName}</code>{' '}
            <button className="btn small ghost" onClick={() => setReplacing(true)}>Upload a different file</button>
          </> : <>
            <p style={{ margin: '0 0 8px' }}>Upload the SQLite database you want to ask questions about.</p>
            <DatabaseUpload onUploaded={() => setReplacing(false)} />
            <div style={{ marginTop: 8, fontSize: 13 }} className="muted">
              {health.database_exists ? 'Or ' : 'No database handy? '}
              {health.database_exists
                ? <button className="btn small ghost" onClick={() => setReplacing(false)}>keep using {fileName}</button>
                : <button className="btn small ghost" onClick={() => create.mutate()} disabled={create.isPending}>
                    {create.isPending ? 'Creating…' : 'Use the sample e-commerce database'}
                  </button>}
            </div>
          </>}
        </Step>
        <Step n={2} done={health.model_connected} title="Language model">
          {health.model_connected
            ? <>Connected to <code>{health.model}</code></>
            : <>
                Connect any OpenAI-compatible model (OpenAI, DeepSeek, OpenRouter, or a local Ollama server).
                <div style={{ marginTop: 8 }}>
                  <button className="btn primary" onClick={onOpenSettings}>Connect a model</button>
                </div>
              </>}
        </Step>
      </ol>
      {create.error && <div className="banner bad" role="alert">{create.error.message}</div>}
    </main>
  );
}

function Step({ n, done, title, children }: { n: number; done: boolean; title: string; children: ReactNode }) {
  return (
    <li className="card" style={{ padding: 14, display: 'flex', gap: 12 }}>
      <span className={`pill ${done ? 'ok' : ''}`} style={{ height: 24, flex: 'none' }}
            aria-label={done ? 'done' : 'to do'}>{done ? '✓' : n}</span>
      <div style={{ fontSize: 13.5, minWidth: 0, flex: 1 }}>
        <strong style={{ display: 'block', fontSize: 14, marginBottom: 2 }}>{title}</strong>
        {children}
      </div>
    </li>
  );
}
