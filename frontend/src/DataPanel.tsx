import { useEffect, useState } from 'react';
import { request } from './api';
import type { DataSource, StorageUse } from './types';

type Pending = { kind: 'delete'; source: DataSource } | { kind: 'clear' } | { kind: 'fresh' };
type Props = {
  busy: boolean;
  onClose(): void;
  onChanged(message: string): Promise<void>;
  onFailed(message: string): void;
  onFreshRun(): Promise<void>;
};

const jobWord = (count: number) => `${count} job${count === 1 ? '' : 's'}`;
// "1 Greenhouse job", "2 Greenhouse jobs"
const boardJobs = (count: number, name: string) => `${count} ${name} job${count === 1 ? '' : 's'}`;
// ", including 1 Applied and 2 with notes" -- only the parts that are non-zero.
const including = (applied: number, withNotes: number) => {
  const parts = [applied && `${applied} Applied`, withNotes && `${withNotes} with notes`].filter(Boolean);
  return parts.length ? `, including ${parts.join(' and ')}` : '';
};

export const formatBytes = (bytes: number | null | undefined) => {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(1)} ${units[unit]}`;
};
// " Storage 1.2 MB → 1.3 MB." for run notices; empty when the run has no both readings.
export const storageChange = (run: { db_bytes_before?: number | null; db_bytes_after?: number | null }) =>
  run.db_bytes_before == null || run.db_bytes_after == null
    ? ''
    : ` Storage ${formatBytes(run.db_bytes_before)} → ${formatBytes(run.db_bytes_after)}.`;

// "2 Applied · 1 with notes · Last run 1.0 MB → 1.2 MB"; Applied/notes only when non-zero, and a run
// with no readings (legacy or interrupted) shows "—".
const rowMeta = (row: DataSource, lastRun: LastRuns[string]) => [
  row.applied ? `${row.applied} Applied` : '',
  row.with_notes ? `${row.with_notes} with notes` : '',
  lastRun ? `Last run ${formatBytes(lastRun.db_bytes_before)} → ${formatBytes(lastRun.db_bytes_after)}` : '',
].filter(Boolean).join(' · ');

type LastRuns = Record<string, { db_bytes_before?: number | null; db_bytes_after?: number | null } | null | undefined>;

export function DataPanel({ busy, onClose, onChanged, onFailed, onFreshRun }: Props) {
  const [sources, setSources] = useState<DataSource[] | null>(null);
  const [storage, setStorage] = useState<StorageUse | null>(null);
  const [lastRuns, setLastRuns] = useState<LastRuns>({});
  const [pending, setPending] = useState<Pending | null>(null);
  const [working, setWorking] = useState(false);
  // A failed load must not look like an empty database.
  const [loadError, setLoadError] = useState('');

  const refresh = async () => {
    try {
      const [rows, use, boards] = await Promise.all([
        request('/data/sources') as Promise<DataSource[]>,
        request('/data/storage') as Promise<StorageUse>,
        request('/sources') as Promise<{ id: string; last_run?: LastRuns[string] }[]>,
      ]);
      setSources(rows);
      setStorage(use);
      setLastRuns(Object.fromEntries(boards.map(board => [board.id, board.last_run])));
      setLoadError('');
    } catch (error) {
      setLoadError((error as Error).message);
    }
  };
  // Also when a run ends: it may have added or removed saved jobs.
  useEffect(() => { refresh(); }, [busy]);

  const totals = (sources ?? []).reduce(
    (sum, row) => ({ jobs: sum.jobs + row.jobs, applied: sum.applied + row.applied, notes: sum.notes + row.with_notes }),
    { jobs: 0, applied: 0, notes: 0 },
  );
  const clearText = totals.jobs
    ? `Clear all data: ${jobWord(totals.jobs)}${including(totals.applied, totals.notes)}? Run history goes too.`
    : 'No saved jobs to clear. Run history goes too.';
  const confirmText = !pending ? '' : pending.kind === 'delete'
    ? `Delete ${boardJobs(pending.source.jobs, pending.source.name)}${including(pending.source.applied, pending.source.with_notes)}? Its run history goes too.`
    : pending.kind === 'clear' ? clearText : `${clearText} Then run AIR and HigherEdJobs.`;

  const confirm = async () => {
    if (!pending || working || busy) return;
    const action = pending;
    setWorking(true);
    try {
      if (action.kind === 'fresh') {
        setPending(null);
        await onFreshRun();
        return;
      }
      const path = action.kind === 'delete' ? `/data/sources/${encodeURIComponent(action.source.source)}` : '/data';
      const result = await request(path, { method: 'DELETE' }) as { deleted: { jobs: number } };
      setPending(null);
      await refresh();
      await onChanged(action.kind === 'delete'
        ? `Deleted ${boardJobs(result.deleted.jobs, action.source.name)}.`
        : `Cleared all data: ${jobWord(result.deleted.jobs)} deleted.`);
    } catch (error) {
      // Nothing changed, so do not reload the jobs view: just show the failure.
      setPending(null);
      await refresh();
      onFailed(`${action.kind === 'delete' ? 'Delete' : 'Clear'} failed: ${(error as Error).message}`);
    } finally {
      setWorking(false);
    }
  };

  const locked = busy || working;
  return <section className="sources data-panel" role="region" aria-label="Data">
    <div className="section-title"><div><h2>Data</h2><p>Saved jobs per job board. Deleting removes the jobs, your Applied status and notes, and that board's run history.</p></div><button className="icon-button" aria-label="Close data" onClick={onClose}>×</button></div>
    {loadError && <p className="data-empty data-error" role="alert">Could not load saved data: {loadError}</p>}
    {sources === null ? (loadError ? null : <p className="data-empty">Loading saved data…</p>) : sources.length === 0
      ? (loadError ? null : <p className="data-empty">No saved data</p>)
      : <ul className="data-list">{sources.map(row => <li key={row.source} className="data-row">
        <b>{row.name}</b>
        <span>{jobWord(row.jobs)}</span>
        <small>{rowMeta(row, lastRuns[row.source])}</small>
        <button className="source-run" aria-label={`Delete ${row.name}`} disabled={locked} onClick={() => setPending({ kind: 'delete', source: row })}>Delete</button>
      </li>)}</ul>}
    {storage && <p className="data-storage">Database {formatBytes(storage.database_bytes)} · Browser session {formatBytes(storage.browser_session_bytes)}</p>}
    <div className="data-actions">
      <button className="source-run" disabled={locked || !sources?.length} onClick={() => setPending({ kind: 'clear' })}>Clear all data</button>
      <button className="source-run" disabled={locked} onClick={() => setPending({ kind: 'fresh' })}>Fresh run</button>
    </div>
    {pending && <div className="data-confirm" role="group" aria-label="Confirm">
      <p>{confirmText}</p>
      <button className="source-run danger" disabled={locked} onClick={confirm}>{pending.kind === 'delete' ? 'Confirm delete' : pending.kind === 'clear' ? 'Confirm clear' : 'Confirm fresh run'}</button>
      <button className="source-run" onClick={() => setPending(null)}>Cancel</button>
    </div>}
  </section>;
}
