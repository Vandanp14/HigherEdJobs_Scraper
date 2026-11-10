import { useEffect, useState } from 'react';
import { request } from './api';
import type { DataSource } from './types';

type Pending = { kind: 'delete'; source: DataSource } | { kind: 'clear' } | { kind: 'fresh' };
type Props = {
  busy: boolean;
  onClose(): void;
  onChanged(message: string): Promise<void>;
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

export function DataPanel({ busy, onClose, onChanged, onFreshRun }: Props) {
  const [sources, setSources] = useState<DataSource[] | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [working, setWorking] = useState(false);

  const refresh = async () => {
    try {
      setSources(await request('/data/sources'));
    } catch {
      setSources(current => current ?? []);
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
      setPending(null);
      await refresh();
      await onChanged((error as Error).message);
    } finally {
      setWorking(false);
    }
  };

  const locked = busy || working;
  return <section className="sources data-panel" role="region" aria-label="Data">
    <div className="section-title"><div><h2>Data</h2><p>Saved jobs per job board. Deleting removes the jobs, your Applied status and notes, and that board's run history.</p></div><button className="icon-button" aria-label="Close data" onClick={onClose}>×</button></div>
    {sources === null ? <p className="data-empty">Loading saved data…</p> : sources.length === 0
      ? <p className="data-empty">No saved data</p>
      : <ul className="data-list">{sources.map(row => <li key={row.source} className="data-row">
        <b>{row.name}</b>
        <span>{jobWord(row.jobs)}</span>
        <small>{row.applied} Applied · {row.with_notes} with notes</small>
        <button className="source-run" aria-label={`Delete ${row.name}`} disabled={locked} onClick={() => setPending({ kind: 'delete', source: row })}>Delete</button>
      </li>)}</ul>}
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
