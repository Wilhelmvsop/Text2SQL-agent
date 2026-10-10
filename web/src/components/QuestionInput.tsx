import { forwardRef } from 'react';

const EXAMPLES = [
  'Which five customers spent the most money in 2025, excluding refunded orders?',
  'List all customers from Canada. Return customer_id and name.',
  'What is the monthly revenue for 2024?',
  'Which product categories have the most refunded orders?',
];

interface Props {
  value: string;
  running: boolean;
  onChange: (value: string) => void;
  onAsk: (question: string) => void;
  onCancel: () => void;
}

export const QuestionInput = forwardRef<HTMLTextAreaElement, Props>(function QuestionInput(
  { value, running, onChange, onAsk, onCancel }, ref) {
  const submit = () => value.trim() && !running && onAsk(value.trim());

  return (
    <>
      <div className="card question">
        <textarea ref={ref} rows={2} value={value} placeholder="Ask a question about your data…"
                  aria-label="Question" maxLength={10_000}
                  onChange={(e) => onChange(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); }
                  }} />
        <div className="question-actions">
          <span className="muted" style={{ fontSize: 12 }}><kbd>Ctrl</kbd> + <kbd>Enter</kbd> to ask</span>
          <span className="spacer" />
          {running
            ? <button className="btn" onClick={onCancel}>Cancel</button>
            : <button className="btn primary" onClick={submit} disabled={!value.trim()}>Ask</button>}
        </div>
      </div>
      {!value && !running && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {EXAMPLES.map((q) => <button key={q} className="chip" onClick={() => onAsk(q)}>{q}</button>)}
        </div>
      )}
    </>
  );
});
