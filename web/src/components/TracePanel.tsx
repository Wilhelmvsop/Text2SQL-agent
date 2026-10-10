import { diffWordsWithSpace } from 'diff';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { Attempt, QueryRecord } from '../api';
import { isAgentTrace } from '../api';
import type { TraceView } from '../workspace';

const STAGES = [
  ['schema_retrieval', 'Retrieve'],
  ['fewshot_retrieval', 'Examples'],
  ['generation_and_validation', 'Generate'],
  ['execution', 'Execute'],
] as const;

interface Props {
  trace: TraceView | null;
  record: QueryRecord | null;
  running: boolean;
}

export function TracePanel({ trace, record, running }: Props) {
  if (record?.kind === 'manual' && record.trace && !isAgentTrace(record.trace)) {
    const v = record.trace.validation;
    return (
      <aside className="trace" aria-label="Trace">
        <h2 style={{ marginBottom: 8 }}>Trace</h2>
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>Hand-edited SQL, run directly without the model.</p>
        <Stage icon={v.valid ? 'ok' : v.retryable ? 'fail' : 'bad'} title="Validate">
          {v.valid ? 'Passed syntax, safety, and EXPLAIN checks.' : <span className="attempt-error">{v.error_type}: {v.error}</span>}
        </Stage>
        {v.valid && <Stage icon={record.status === 'success' ? 'ok' : 'bad'} title="Execute" time={record.latency}>
          {record.status === 'success' ? `${record.row_count} rows` : record.error}
        </Stage>}
        {record.parent_id && <Link to={`/q/${record.parent_id}`} style={{ fontSize: 13 }}>← Original question and agent trace</Link>}
      </aside>
    );
  }

  if (!trace) {
    return (
      <aside className="trace" aria-label="Trace">
        <h2>Trace</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          Each step the agent takes appears here: which tables it chose, the examples it used, every SQL attempt, and how long each step took.
        </p>
      </aside>
    );
  }

  const last = trace.attempts.at(-1);
  const genDone = !!last && (last.validation.valid || !running);
  const icon = (done: boolean, failed = false): StageIcon => done ? (failed ? 'bad' : 'ok') : running ? 'running' : 'idle';

  return (
    <aside className="trace" aria-label="Trace" aria-live="polite" aria-busy={running}>
      <h2 style={{ marginBottom: 8 }}>Trace</h2>

      <Stage icon={icon(!!trace.tables)} title="Retrieve tables" time={trace.latencies.schema_retrieval}>
        {trace.tables && trace.scores && trace.tables.map((t) => {
          const score = trace.scores![t];
          return (
            <div key={t} className="score-row">
              <span className="mono">{t}</span>
              {score === null ? <span className="muted" style={{ gridColumn: 'span 2' }}>full schema</span> : <>
                <div className="bar"><div style={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }} /></div>
                <span className="mono muted">{score.toFixed(2)}</span>
              </>}
            </div>
          );
        })}
      </Stage>

      <Stage icon={icon(!!trace.examples)} title="Pick examples" time={trace.latencies.fewshot_retrieval}>
        {trace.examples?.length === 0 && <span className="muted">No compatible examples.</span>}
        {trace.examples?.map((hit) => (
          <details key={hit.example.id} className="fold">
            <summary>{hit.example.id} · {hit.example.question}</summary>
            <pre>{hit.example.sql}</pre>
          </details>
        ))}
      </Stage>

      {trace.attempts.map((attempt, i) => (
        <AttemptStage key={attempt.number} attempt={attempt} previous={trace.attempts[i - 1]} />
      ))}
      {running && !genDone && trace.examples && (
        <Stage icon="running" title={trace.attempts.length ? 'Correcting SQL' : 'Generating SQL'} />
      )}

      {(trace.executed || (genDone && last?.validation.valid)) && (
        <Stage icon={trace.executed ? 'ok' : record?.status === 'error' ? 'bad' : 'running'} title="Execute"
               time={trace.latencies.execution}>
          {record?.status === 'error' && <span className="attempt-error">{record.error}</span>}
          {record?.result && <span className="muted">{record.row_count} rows returned</span>}
        </Stage>
      )}

      {!running && record && <Summary trace={trace} record={record} />}
    </aside>
  );
}

function AttemptStage({ attempt, previous }: { attempt: Attempt; previous?: Attempt }) {
  const [showDiff, setShowDiff] = useState(false);
  const v = attempt.validation;
  const sql = v.sql || attempt.raw_output;
  return (
    <Stage icon={v.valid ? 'ok' : v.retryable ? 'fail' : 'bad'}
           title={attempt.number === 1 ? 'Attempt 1' : `Attempt ${attempt.number} (correction)`}
           time={attempt.generation_latency}>
      {v.valid ? <span className="muted">Passed validation</span>
        : <span className="attempt-error">{v.retryable ? '' : '⛔ '}{v.error_type}: {v.error}</span>}
      <details className="fold">
        <summary>SQL</summary>
        <pre>{sql}</pre>
      </details>
      {previous && (
        <button className="btn small" style={{ alignSelf: 'flex-start' }} onClick={() => setShowDiff(!showDiff)}
                aria-expanded={showDiff}>
          {showDiff ? 'Hide' : 'Compare with'} attempt {previous.number}
        </button>
      )}
      {showDiff && previous && <SqlDiff before={previous.validation.sql || previous.raw_output} after={sql} />}
    </Stage>
  );
}

export function SqlDiff({ before, after }: { before: string; after: string }) {
  return (
    <div className="diff" aria-label={`Changes between attempts`}>
      {diffWordsWithSpace(before, after).map((part, i) =>
        <span key={i} className={part.added ? 'add' : part.removed ? 'del' : ''}>{part.value}</span>)}
    </div>
  );
}

function Summary({ trace, record }: { trace: TraceView; record: QueryRecord }) {
  const total = STAGES.reduce((sum, [key]) => sum + (trace.latencies[key] ?? 0), 0);
  const retries = trace.attempts.length - 1;
  return (
    <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, marginTop: 4, fontSize: 13 }}>
      {record.status === 'success' && retries > 0 && (
        <div className="pill accent" style={{ marginBottom: 8 }}>Fixed after {retries} {retries === 1 ? 'retry' : 'retries'}</div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <strong>Latency</strong><span className="mono">{record.latency.toFixed(2)}s</span>
      </div>
      <div className="latency" role="img" aria-label="Time spent per stage">
        {STAGES.map(([key]) => <div key={key} style={{ width: `${total ? ((trace.latencies[key] ?? 0) / total) * 100 : 0}%` }} />)}
      </div>
      <div className="legend">
        {STAGES.map(([key, label], i) => (
          <span key={key}><i style={{ background: ['#7c95f5', '#63c5b8', '#f0a83c', '#5ac46f'][i] }} />
            {label} {(trace.latencies[key] ?? 0).toFixed(2)}s</span>
        ))}
      </div>
      {trace.tokens.total_tokens !== undefined && (
        <div style={{ marginTop: 8 }} className="muted">
          Tokens: {trace.tokens.total_tokens.toLocaleString()} ({trace.tokens.prompt_tokens ?? 0} prompt, {trace.tokens.completion_tokens ?? 0} completion)
        </div>
      )}
    </div>
  );
}

type StageIcon = 'ok' | 'fail' | 'bad' | 'running' | 'idle';

function Stage({ icon, title, time, children }: { icon: StageIcon; title: string; time?: number; children?: ReactNode }) {
  const label = { ok: 'done', fail: 'failed, retrying', bad: 'failed', running: 'in progress', idle: 'pending' }[icon];
  return (
    <div className="stage">
      <span className={`stage-icon ${icon}`} role="img" aria-label={label} />
      <div className="stage-title">{title}{time !== undefined && <span className="time">{time.toFixed(2)}s</span>}</div>
      {children && <div className="stage-body">{children}</div>}
    </div>
  );
}
