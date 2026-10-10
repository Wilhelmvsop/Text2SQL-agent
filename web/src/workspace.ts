import type { Attempt, FewShotHit, QueryRecord, StreamEvent } from './api';
import { isAgentTrace } from './api';

/** The trace as it is known so far: filled event by event while streaming, or from a saved record. */
export interface TraceView {
  tables?: string[];
  scores?: Record<string, number | null>;
  examples?: FewShotHit[];
  attempts: Attempt[];
  latencies: Record<string, number>;
  tokens: Record<string, number>;
  executed: boolean;
}

export interface WorkspaceState {
  question: string;
  sql: string;
  /** SQL the editor content is compared against to show the "Edited" tag. */
  baseSql: string;
  record: QueryRecord | null;
  trace: TraceView | null;
  running: boolean;
  error: string | null;
}

export type Action =
  | { type: 'reset' }
  | { type: 'question'; question: string }
  | { type: 'sql'; sql: string }
  | { type: 'start'; question: string }
  | { type: 'event'; event: StreamEvent }
  | { type: 'load'; record: QueryRecord }
  | { type: 'failed'; error: string }
  | { type: 'cancelled' };

export const initialState: WorkspaceState = {
  question: '', sql: '', baseSql: '', record: null, trace: null, running: false, error: null,
};

const emptyTrace = (): TraceView => ({ attempts: [], latencies: {}, tokens: {}, executed: false });

export function traceFromRecord(record: QueryRecord): TraceView | null {
  const trace = record.trace;
  if (!isAgentTrace(trace)) return null;
  return {
    tables: trace.retrieved_tables,
    scores: trace.retrieval_scores,
    examples: trace.fewshot_examples,
    attempts: trace.validation_attempts,
    latencies: trace.stage_latencies,
    tokens: trace.token_usage,
    executed: 'execution' in trace.stage_latencies,
  };
}

export function reducer(state: WorkspaceState, action: Action): WorkspaceState {
  switch (action.type) {
    case 'reset':
      return initialState;
    case 'question':
      return { ...state, question: action.question };
    case 'sql':
      return { ...state, sql: action.sql };
    case 'start':
      return { ...initialState, question: action.question, trace: emptyTrace(), running: true };
    case 'cancelled':
      return { ...state, running: false, error: 'Cancelled. The server may still finish and save this run to history.' };
    case 'failed':
      return { ...state, running: false, error: action.error };
    case 'load': {
      const sql = action.record.final_sql ?? lastAttemptSql(action.record) ?? '';
      return {
        ...initialState, question: action.record.question, sql, baseSql: sql,
        record: action.record, trace: traceFromRecord(action.record),
      };
    }
    case 'event':
      return applyEvent(state, action.event);
  }
}

function applyEvent(state: WorkspaceState, event: StreamEvent): WorkspaceState {
  const trace = state.trace ?? emptyTrace();
  switch (event.stage) {
    case 'schema_retrieval':
      return { ...state, trace: { ...trace, tables: event.data.tables, scores: event.data.scores,
        latencies: { ...trace.latencies, schema_retrieval: event.data.latency } } };
    case 'fewshot_retrieval':
      return { ...state, trace: { ...trace, examples: event.data.examples,
        latencies: { ...trace.latencies, fewshot_retrieval: event.data.latency } } };
    case 'attempt': {
      const sql = event.data.validation.sql || event.data.raw_output;
      return { ...state, sql, baseSql: sql, trace: { ...trace, attempts: [...trace.attempts, event.data] } };
    }
    case 'execution':
      return { ...state, trace: { ...trace, executed: true,
        latencies: { ...trace.latencies, execution: event.data.latency } } };
    case 'done':
      return reducer(state, { type: 'load', record: event.data });
    case 'error':
      return { ...state, running: false, error: event.data.detail };
  }
}

function lastAttemptSql(record: QueryRecord): string | null {
  if (!isAgentTrace(record.trace)) return null;
  const last = record.trace.validation_attempts.at(-1);
  return last ? last.validation.sql || last.raw_output : null;
}

/** The agent run a manual edit belongs to, so re-runs nest under their original question. */
export const rootId = (record: QueryRecord | null): string | null =>
  record ? (record.kind === 'agent' ? record.id : record.parent_id ?? record.id) : null;
