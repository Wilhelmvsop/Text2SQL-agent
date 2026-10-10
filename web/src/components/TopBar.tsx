import type { Health } from '../api';

interface Props {
  health: Health | undefined;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onOpenSchema: () => void;
  onOpenSettings: () => void;
  onNew: () => void;
  panes: { left: boolean; right: boolean };
  onTogglePane: (side: 'left' | 'right') => void;
}

export function TopBar({ health, theme, onToggleTheme, onOpenSchema, onOpenSettings, onNew, panes, onTogglePane }: Props) {
  const fileName = health?.db_path.split(/[\\/]/).pop();
  return (
    <header className="topbar">
      <div className="brand"><span className="brand-mark" aria-hidden>◆</span> Text2SQL</div>
      {fileName && <span className="pill mono hide-narrow" title={health?.db_path}>{fileName}</span>}
      <div className="spacer" />
      {health && (
        <button className={`pill ${health.model_connected ? 'ok' : 'bad'}`}
                style={{ border: 0, cursor: 'pointer' }} onClick={onOpenSettings}
                title="Model settings">
          <span aria-hidden>●</span>
          <span>{health.model_connected ? health.model : 'No model connected'}</span>
        </button>
      )}
      <button className="btn ghost small" onClick={onNew}>+ New</button>
      <button className="btn ghost small" onClick={onOpenSchema} disabled={!health?.ready}>Schema</button>
      <span className="hide-narrow">
        <button className="icon-btn" aria-pressed={panes.left} onClick={() => onTogglePane('left')}
                title="Toggle history ( [ )" aria-label="Toggle history panel">◧</button>
        <button className="icon-btn" aria-pressed={panes.right} onClick={() => onTogglePane('right')}
                title="Toggle trace ( ] )" aria-label="Toggle trace panel">◨</button>
      </span>
      <button className="icon-btn" onClick={onToggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
        {theme === 'dark' ? '☀' : '☾'}
      </button>
      <button className="btn small" onClick={onOpenSettings}>⚙ Settings</button>
    </header>
  );
}
