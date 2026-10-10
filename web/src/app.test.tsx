import { render, screen } from '@testing-library/react';
import type { Attempt, QueryRecord } from './api';
import { parseEvent } from './api';
import { ResultsTable, toCsv } from './components/ResultsTable';
import { initialState, reducer, rootId } from './workspace';

const attempt = (number: number, valid: boolean, sql: string): Attempt => ({
  number, raw_output: sql, prompt_chars: 0, generation_latency: 0.1, usage: {},
  validation: { valid, sql, error: valid ? null : 'no such column: nme', error_type: valid ? null : 'unknown_column',
    stage: 'explain', retryable: true },
});

const record = (overrides: Partial<QueryRecord> = {}): QueryRecord => ({
  id: 'abc123', kind: 'agent', parent_id: null, question: 'q', status: 'success', error: null, error_type: null,
  final_sql: 'SELECT 1', result: { columns: ['n'], rows: [[1]], truncated: false }, row_count: 1, latency: 0.5,
  trace: null, starred: false, created_at: new Date().toISOString(), ...overrides,
});

describe('workspace reducer', () => {
  it('builds the trace from stream events, then loads the saved record', () => {
    let state = reducer(initialState, { type: 'start', question: 'Top customers?' });
    expect(state.running).toBe(true);
    state = reducer(state, { type: 'event', event: { stage: 'schema_retrieval',
      data: { tables: ['customers'], scores: { customers: 0.8 }, latency: 0.01 } } });
    state = reducer(state, { type: 'event', event: { stage: 'attempt', data: attempt(1, false, 'SELECT nme FROM customers') } });
    expect(state.sql).toBe('SELECT nme FROM customers');
    state = reducer(state, { type: 'event', event: { stage: 'attempt', data: attempt(2, true, 'SELECT name FROM customers') } });
    expect(state.trace?.attempts).toHaveLength(2);
    expect(state.trace?.tables).toEqual(['customers']);

    state = reducer(state, { type: 'event', event: { stage: 'done', data: record({ final_sql: 'SELECT name FROM customers' }) } });
    expect(state.running).toBe(false);
    expect(state.baseSql).toBe('SELECT name FROM customers');
  });

  it('stops running and keeps the message on a stream error', () => {
    const state = reducer(reducer(initialState, { type: 'start', question: 'x' }),
      { type: 'event', event: { stage: 'error', data: { detail: 'Provider HTTP 401' } } });
    expect(state).toMatchObject({ running: false, error: 'Provider HTTP 401' });
  });

  it('nests manual re-runs under the original agent run', () => {
    expect(rootId(record())).toBe('abc123');
    expect(rootId(record({ id: 'm1', kind: 'manual', parent_id: 'abc123' }))).toBe('abc123');
    expect(rootId(null)).toBeNull();
  });
});

describe('helpers', () => {
  it('parses server-sent event blocks', () => {
    expect(parseEvent('event: execution\ndata: {"latency": 0.2}')).toEqual({ stage: 'execution', data: { latency: 0.2 } });
    expect(parseEvent(': keep-alive')).toBeNull();
  });

  it('quotes CSV cells that need it', () => {
    expect(toCsv(['a', 'b'], [['x,y', null], ['say "hi"', 2]])).toBe('a,b\r\n"x,y",\r\n"say ""hi""",2');
  });
});

describe('ResultsTable', () => {
  it('distinguishes zero rows from an error', () => {
    render(<ResultsTable record={record({ result: { columns: ['n'], rows: [], truncated: false } })} running={false} maxRows={1000} />);
    expect(screen.getByText(/returned 0 rows/)).toBeTruthy();
  });

  it('labels safety rejections', () => {
    render(<ResultsTable record={record({ status: 'validation_failed', result: null, error_type: 'unsafe',
      error: 'Only SELECT statements are allowed' })} running={false} maxRows={1000} />);
    expect(screen.getByRole('alert').textContent).toMatch(/blocked for safety/);
  });

  it('warns when the row limit truncated the results', () => {
    render(<ResultsTable record={record({ result: { columns: ['n'], rows: [[1]], truncated: true } })} running={false} maxRows={1000} />);
    expect(screen.getByText(/row limit was reached/)).toBeTruthy();
  });
});
