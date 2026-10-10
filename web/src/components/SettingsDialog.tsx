import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api, type Health, type Settings, type SettingsUpdate } from '../api';
import { DatabaseUpload } from './DatabaseUpload';

const PRESETS = [
  { label: 'OpenAI', url: 'https://api.openai.com/v1' },
  { label: 'DeepSeek', url: 'https://api.deepseek.com/v1' },
  { label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { label: 'Ollama (local)', url: 'http://localhost:11434/v1' },
];

type Form = Omit<Settings, 'api_key_set' | 'embedding_api_key_set'>;
/** undefined = keep the saved secret, '' = clear it, anything else = replace it. */
type Secrets = { api_key?: string; embedding_api_key?: string };

interface Props {
  health: Health | undefined;
  onClose: () => void;
}

export function SettingsDialog({ health, onClose }: Props) {
  const client = useQueryClient();
  const { data: saved, isLoading } = useQuery({ queryKey: ['settings'], queryFn: api.settings });
  const [form, setForm] = useState<Form | null>(null);
  const [secrets, setSecrets] = useState<Secrets>({});
  const [test, setTest] = useState<{ ok: boolean; message: string } | null>(null);
  const dialog = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (saved && !form) {
      const { api_key_set: _a, embedding_api_key_set: _b, ...rest } = saved;
      setForm(rest);
    }
  }, [saved, form]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    dialog.current?.querySelector<HTMLElement>('input, button')?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const update = (): SettingsUpdate => ({ ...form!, ...Object.fromEntries(
    Object.entries(secrets).filter(([, v]) => v !== undefined)) });
  const refresh = () => Promise.all(['health', 'settings', 'schema'].map((k) =>
    client.invalidateQueries({ queryKey: [k] })));

  const save = useMutation({
    mutationFn: () => api.saveSettings(update()),
    onSuccess: async () => { await refresh(); onClose(); },
  });
  const reset = useMutation({
    mutationFn: api.resetSettings,
    onSuccess: async (settings) => {
      const { api_key_set: _a, embedding_api_key_set: _b, ...rest } = settings;
      setForm(rest); setSecrets({}); await refresh();
    },
  });
  const testConnection = useMutation({
    mutationFn: () => api.testSettings(update()),
    onMutate: () => setTest(null),
    onSuccess: setTest,
    onError: (e: Error) => setTest({ ok: false, message: e.message }),
  });
  const createDemo = useMutation({
    mutationFn: async () => { await api.saveSettings(update()); return api.createDemoDatabase(); },
    onSuccess: refresh,
  });

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => f && { ...f, [key]: value });
  const pathChanged = form && saved && form.db_path !== saved.db_path;
  const error = save.error ?? reset.error ?? createDemo.error;

  return (
    <div className="overlay center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title" ref={dialog}>
        <div className="dialog-head">
          <h1 id="settings-title">Settings</h1>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {isLoading || !form || !saved ? <div className="dialog-body"><div className="skeleton" /></div> : (
          <form className="dialog-body" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <fieldset>
              <legend>Language model</legend>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                Required. The app sends a short test request when you save, and only saves a model that answers.
              </p>
              <>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {PRESETS.map((p) => (
                    <button type="button" key={p.label} className="chip" aria-pressed={form.base_url === p.url}
                            onClick={() => set('base_url', p.url)}>{p.label}</button>
                  ))}
                </div>
                <Field label="API base URL" hint="Any OpenAI-compatible Chat Completions endpoint.">
                  <input type="text" value={form.base_url} onChange={(e) => set('base_url', e.target.value)} required />
                </Field>
                <div className="row">
                  <Field label="Model">
                    <input type="text" value={form.model} placeholder="e.g. gpt-4o-mini" onChange={(e) => set('model', e.target.value)} required />
                  </Field>
                  <SecretField label="API key" isSet={saved.api_key_set} value={secrets.api_key}
                               onChange={(v) => setSecrets((s) => ({ ...s, api_key: v }))} />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <button type="button" className="btn small" onClick={() => testConnection.mutate()}
                          disabled={testConnection.isPending || !form.model}>
                    {testConnection.isPending ? 'Testing…' : 'Test connection'}
                  </button>
                  {test && <span className={`pill ${test.ok ? 'ok' : 'bad'}`} role="status"><span>{test.ok ? '✓' : '✗'} {test.message}</span></span>}
                </div>
              </>
            </fieldset>

            <fieldset>
              <legend>Table retrieval</legend>
              <Field label="Embedding method" hint={{
                hashing: 'Fast and offline. Good for the demo database.',
                'sentence-transformers': 'Better matching; runs locally. Requires installing the [neural] extra.',
                api: 'Uses an OpenAI-compatible embeddings endpoint.',
              }[form.embedding]}>
                <select value={form.embedding} onChange={(e) => set('embedding', e.target.value as Form['embedding'])}>
                  <option value="hashing">Hashing (built in)</option>
                  <option value="sentence-transformers">Sentence Transformers (local)</option>
                  <option value="api">Embeddings API</option>
                </select>
              </Field>
              {form.embedding !== 'hashing' && (
                <Field label="Embedding model">
                  <input type="text" value={form.embedding_model} onChange={(e) => set('embedding_model', e.target.value)} />
                </Field>
              )}
              {form.embedding === 'api' && (
                <div className="row">
                  <Field label="Embeddings base URL">
                    <input type="text" value={form.embedding_base_url} onChange={(e) => set('embedding_base_url', e.target.value)} />
                  </Field>
                  <SecretField label="Embeddings API key" isSet={saved.embedding_api_key_set} value={secrets.embedding_api_key}
                               onChange={(v) => setSecrets((s) => ({ ...s, embedding_api_key: v }))} />
                </div>
              )}
              <div className="row">
                <Field label="Tables to retrieve" hint="How many of the most relevant tables the model sees (1–20).">
                  <input type="number" min={1} max={20} value={form.top_k}
                         onChange={(e) => set('top_k', Number(e.target.value))} required />
                </Field>
                <Field label="Correction retries" hint="Extra attempts after invalid SQL (0–10).">
                  <input type="number" min={0} max={10} value={form.max_retries}
                         onChange={(e) => set('max_retries', Number(e.target.value))} required />
                </Field>
              </div>
            </fieldset>

            <fieldset>
              <legend>Database</legend>
              <DatabaseUpload compact onUploaded={(path) => set('db_path', path)} />
              <Field label="Or enter a path on this computer" hint="Opened read-only. Paths are relative to where the server was started.">
                <input type="text" className="mono" value={form.db_path} onChange={(e) => set('db_path', e.target.value)} required />
              </Field>
              {!pathChanged && health && !health.database_exists && (
                <div className="banner info">
                  No database at this path yet.{' '}
                  <button type="button" className="btn small" onClick={() => createDemo.mutate()} disabled={createDemo.isPending}>
                    {createDemo.isPending ? 'Creating…' : 'Create demo database here'}
                  </button>
                </div>
              )}
              {pathChanged && <small className="muted">Save to check the new path.</small>}
              {createDemo.isSuccess && <span className="pill ok">✓ Demo database created</span>}
            </fieldset>

            {error && <div className="banner bad" role="alert">{(error as Error).message}</div>}
            <div className="muted" style={{ fontSize: 12 }}>
              Settings and API keys are stored on this computer in the app database and are never sent back to the browser.
            </div>
            <button type="submit" hidden />
          </form>
        )}

        <div className="dialog-foot">
          <button className="btn ghost danger" onClick={() => confirm('Reset all settings to their defaults?') && reset.mutate()}
                  disabled={reset.isPending}>Reset to defaults</button>
          <span className="spacer" />
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={() => save.mutate()} disabled={!form || save.isPending}>
            {save.isPending ? 'Connecting…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}

function SecretField({ label, isSet, value, onChange }: {
  label: string; isSet: boolean; value: string | undefined; onChange: (v: string | undefined) => void;
}) {
  const cleared = value === '' && isSet;
  return (
    <Field label={label} hint={cleared ? 'Will be removed when you save.' : isSet ? 'Saved. Leave blank to keep it.' : 'Optional for local servers.'}>
      <div style={{ display: 'flex', gap: 6 }}>
        <input type="password" autoComplete="off" value={value ?? ''} placeholder={isSet && !cleared ? '••••••••' : ''}
               onChange={(e) => onChange(e.target.value || undefined)} />
        {isSet && !value && !cleared && <button type="button" className="btn small" onClick={() => onChange('')}>Remove</button>}
        {cleared && <button type="button" className="btn small" onClick={() => onChange(undefined)}>Undo</button>}
      </div>
    </Field>
  );
}
