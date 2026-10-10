export type Status = 'running' | 'success' | 'validation_failed' | 'error';

export interface Validation {
  valid: boolean;
  sql: string;
  error: string | null;
  error_type: string | null;
  stage: string;
  retryable: boolean;
}

export interface Attempt {
  number: number;
  raw_output: string;
  validation: Validation;
  prompt_chars: number;
  generation_latency: number;
  usage: Record<string, number>;
}

export interface FewShotHit {
  example: { id: string; question: string; sql: string };
  score: number;
}

export interface AgentTrace {
  trace_id: string;
  provider: string;
  embedding_provider: string;
  retrieved_tables: string[];
  retrieval_scores: Record<string, number | null>;
  fewshot_examples: FewShotHit[];
  validation_attempts: Attempt[];
  stage_latencies: Record<string, number>;
  token_usage: Record<string, number>;
}

export interface ManualTrace {
  validation: Validation;
}

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
}

export interface QueryRecord {
  id: string;
  kind: 'agent' | 'manual';
  parent_id: string | null;
  question: string;
  status: Status;
  error: string | null;
  error_type: string | null;
  final_sql: string | null;
  result: QueryResult | null;
  row_count: number | null;
  latency: number;
  trace: AgentTrace | ManualTrace | null;
  starred: boolean;
  created_at: string;
}

export type HistoryItem = Omit<QueryRecord, 'result' | 'trace' | 'error'>;

export interface Health {
  ready: boolean;
  error: string | null;
  model_connected: boolean;
  model: string;
  database_exists: boolean;
  db_path: string;
  max_rows: number | null;
}

export interface Settings {
  db_path: string;
  base_url: string;
  model: string;
  embedding: 'hashing' | 'sentence-transformers' | 'api';
  embedding_model: string;
  embedding_base_url: string;
  top_k: number;
  max_retries: number;
  api_key_set: boolean;
  embedding_api_key_set: boolean;
}

/** Secrets are write-only: undefined keeps the stored value, '' clears it. */
export type SettingsUpdate = Partial<Omit<Settings, 'api_key_set' | 'embedding_api_key_set'>> & {
  api_key?: string;
  embedding_api_key?: string;
};

export interface TableSchema {
  name: string;
  description: string;
  columns: { name: string; type: string; primary_key: boolean; nullable: boolean }[];
  foreign_keys: { column: string; target_table: string; target_column: string }[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  });
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return response.status === 204 ? (undefined as T) : response.json();
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join('; ');
  } catch {
    /* non-JSON error body */
  }
  return `Request failed (${response.status})`;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>('/health'),
  schema: () => request<{ tables: TableSchema[] }>('/schema'),
  settings: () => request<Settings>('/settings'),
  saveSettings: (update: SettingsUpdate) => request<Settings>('/settings', json('PUT', update)),
  resetSettings: () => request<Settings>('/settings', { method: 'DELETE' }),
  testSettings: (update: SettingsUpdate) =>
    request<{ ok: boolean; message: string }>('/settings/test', json('POST', update)),
  createDemoDatabase: () => request<{ db_path: string }>('/database/demo', { method: 'POST' }),
  validate: (sql: string, signal?: AbortSignal) =>
    request<Validation>('/sql/validate', { ...json('POST', { sql }), signal }),
  execute: (sql: string, question: string, parentId: string | null) =>
    request<QueryRecord>('/sql/execute', json('POST', { sql, question, parent_id: parentId })),
  history: (params: { search?: string; status?: string; starred?: boolean }) => {
    const query = new URLSearchParams();
    if (params.search) query.set('search', params.search);
    if (params.status) query.set('status', params.status);
    if (params.starred !== undefined) query.set('starred', String(params.starred));
    return request<{ items: HistoryItem[]; total: number }>(`/history?${query}`);
  },
  record: (id: string) => request<QueryRecord>(`/history/${id}`),
  star: (id: string, starred: boolean) => request(`/history/${id}`, json('PATCH', { starred })),
  remove: (id: string) => request<void>(`/history/${id}`, { method: 'DELETE' }),
};

export type StreamEvent =
  | { stage: 'schema_retrieval'; data: { tables: string[]; scores: Record<string, number | null>; latency: number } }
  | { stage: 'fewshot_retrieval'; data: { examples: FewShotHit[]; latency: number } }
  | { stage: 'attempt'; data: Attempt }
  | { stage: 'execution'; data: { latency: number } }
  | { stage: 'done'; data: QueryRecord }
  | { stage: 'error'; data: { detail: string } };

/** POST a question and yield server-sent events as each pipeline stage finishes. */
export async function* askStream(question: string, signal: AbortSignal): AsyncGenerator<StreamEvent> {
  const response = await fetch('/api/queries/stream', { ...json('POST', { question }), signal,
    headers: { 'Content-Type': 'application/json' } });
  if (!response.ok || !response.body) throw new ApiError(response.status, await errorMessage(response));
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    let boundary: number;
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const event = parseEvent(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (event) yield event;
    }
  }
}

export function parseEvent(block: string): StreamEvent | null {
  let stage = '';
  let data = '';
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) stage = line.slice(7);
    else if (line.startsWith('data: ')) data += line.slice(6);
  }
  return stage && data ? ({ stage, data: JSON.parse(data) } as StreamEvent) : null;
}

export const isAgentTrace = (trace: QueryRecord['trace']): trace is AgentTrace =>
  !!trace && 'validation_attempts' in trace;

export const UPLOAD_LIMIT_MB = 200;

/** Upload a SQLite file; the server validates it and switches the app to it. */
export function uploadDatabase(file: File, onProgress: (fraction: number) => void,
                               signal?: AbortSignal): Promise<{ db_path: string; name: string; tables: number }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/database/upload?${new URLSearchParams({ filename: file.name })}`);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body: { detail?: unknown } = {};
      try { body = JSON.parse(xhr.responseText); } catch { /* non-JSON error page */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as never);
      else reject(new ApiError(xhr.status, typeof body.detail === 'string' ? body.detail : `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new ApiError(0, 'Upload failed: could not reach the server'));
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'));
    signal?.addEventListener('abort', () => xhr.abort());
    xhr.send(file);
  });
}
