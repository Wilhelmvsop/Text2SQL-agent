import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type DragEvent } from 'react';
import { UPLOAD_LIMIT_MB, uploadDatabase } from '../api';

const ACCEPT = '.db,.sqlite,.sqlite3,.db3';

type Upload =
  | { state: 'idle' }
  | { state: 'uploading'; name: string; progress: number }
  | { state: 'done'; name: string; tables: number }
  | { state: 'error'; message: string };

interface Props {
  /** Smaller single-row layout for the settings dialog. */
  compact?: boolean;
  onUploaded?: (dbPath: string) => void;
}

/** Drop or pick a SQLite file; the server validates it and the app switches to it. */
export function DatabaseUpload({ compact = false, onUploaded }: Props) {
  const client = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const [upload, setUpload] = useState<Upload>({ state: 'idle' });
  const [over, setOver] = useState(false);

  useEffect(() => () => abort.current?.abort(), []);

  const start = async (file: File) => {
    if (file.size > UPLOAD_LIMIT_MB * 1024 * 1024) {
      setUpload({ state: 'error', message: `${file.name} is larger than the ${UPLOAD_LIMIT_MB} MB limit.` });
      return;
    }
    abort.current = new AbortController();
    setUpload({ state: 'uploading', name: file.name, progress: 0 });
    try {
      const result = await uploadDatabase(file, (progress) =>
        setUpload({ state: 'uploading', name: file.name, progress }), abort.current.signal);
      setUpload({ state: 'done', name: file.name, tables: result.tables });
      await client.invalidateQueries();
      onUploaded?.(result.db_path);
    } catch (e) {
      const error = e as Error;
      setUpload(error.name === 'AbortError' ? { state: 'idle' } : { state: 'error', message: error.message });
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const file = e.dataTransfer.files[0];
    if (file && upload.state !== 'uploading') start(file);
  };

  const busy = upload.state === 'uploading';
  return (
    <div>
      <div className={`dropzone ${compact ? 'compact' : ''} ${over ? 'over' : ''}`}
           onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
        {busy ? <>
          <span style={{ fontSize: 13 }}>Uploading <strong>{upload.name}</strong>… {Math.round(upload.progress * 100)}%</span>
          <div className="progress" role="progressbar" aria-valuenow={Math.round(upload.progress * 100)}
               aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress">
            <div style={{ width: `${upload.progress * 100}%` }} />
          </div>
          <button type="button" className="btn small" onClick={() => abort.current?.abort()}>Cancel</button>
        </> : <>
          {!compact && <span aria-hidden style={{ fontSize: 22 }}>⇪</span>}
          <span style={{ fontSize: 13 }}>Drag a SQLite database file here, or</span>
          <button type="button" className="btn primary small" onClick={() => input.current?.click()}>Choose file</button>
          {!compact && <span className="hint">.db, .sqlite, or .sqlite3 · up to {UPLOAD_LIMIT_MB} MB · opened read-only</span>}
        </>}
        <input ref={input} type="file" accept={ACCEPT} hidden aria-label="Database file"
               onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ''; if (file) start(file); }} />
      </div>
      <div aria-live="polite">
        {upload.state === 'done' && (
          <div className="banner info" style={{ marginTop: 8 }}>
            ✓ Connected to <strong>{upload.name}</strong> ({upload.tables} {upload.tables === 1 ? 'table' : 'tables'}).
          </div>
        )}
        {upload.state === 'error' && <div className="banner bad" role="alert" style={{ marginTop: 8 }}>{upload.message}</div>}
      </div>
    </div>
  );
}
