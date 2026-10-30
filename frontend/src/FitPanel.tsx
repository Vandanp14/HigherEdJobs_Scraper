import { ExternalLink, PanelRightClose } from 'lucide-react';
import { postedLabel } from './forYou';
import { signalClass, type Job } from './types';

type Props = {
  job: Job | null;
  onCollapse: () => void;
  onOpen: (job: Job) => void;
  onApplied: (job: Job) => void;
};

// Explains how age moved a job: inside 30 days the rank is fit adjusted for age; older jobs sit below all of them.
const ageLine = (job: Job) => {
  if (job.fit_score === null) return null;
  if (job.age_days === null || job.age_days > 30) return 'Posted more than 30 days ago, so it ranks below every newer job.';
  if (Math.abs(job.rank_value - job.fit_score) < 0.1) return null;
  return `Fit ${job.fit_score}, ${postedLabel(job.age_days).toLowerCase()}, ranked as ${job.rank_value.toFixed(1)}.`;
};

export function FitPanel({ job, onCollapse, onOpen, onApplied }: Props) {
  if (!job) return <aside className="fit-panel" aria-label="Fit details"><p className="fit-panel-empty">Select a job to see why it ranks where it does.</p></aside>;
  const details = job.fit_details;
  const missing = [...(details.declined ?? []), ...(details.missing ?? [])];
  const age = ageLine(job);

  return <aside className="fit-panel" aria-label="Fit details">
    <div className="fit-panel-head">
      <div><h3>{job.title || 'Untitled listing'}</h3><span>{[job.institution, job.location, postedLabel(job.age_days)].filter(Boolean).join(' · ')}</span></div>
      <b className="fit-panel-score">{job.fit_score ?? '–'}</b>
    </div>
    <button className="fit-panel-collapse" aria-label="Collapse fit details" title="Collapse (Esc)" onClick={onCollapse}><PanelRightClose size={16} /></button>
    <div className="fit-parts">
      <div><b>{details.required_total ? `${details.required_matched} of ${details.required_total}` : '—'}</b><span>required skills you have</span></div>
      <div><span className={'signal ' + signalClass(job.sponsorship_status)}>{job.sponsorship_status}</span><span>sponsorship wording</span></div>
      <div><b>{job.seniority_flags.length ? job.seniority_flags.map(flag => flag.label).join(', ') : 'None'}</b><span>seniority flags</span></div>
    </div>
    {age && <p className="fit-age">{age}</p>}
    <h4>Matched from your resume</h4>
    <div className="fit-tags">{(details.matched ?? []).length ? details.matched!.map(skill => <span key={skill} className="fit-tag fit-match">{skill}</span>) : <span className="fit-none">No listed skills matched.</span>}</div>
    <h4>Missing</h4>
    <div className="fit-tags">{missing.length ? missing.map(skill => <span key={skill} className="fit-tag fit-gap">{skill}</span>) : <span className="fit-none">Nothing the posting names is missing.</span>}</div>
    {(details.reasons ?? []).some(reason => reason.startsWith('Description not captured')) && <p className="fit-none">Description not captured; skills not checked.</p>}
    <h4>Sponsorship</h4>
    <blockquote className="fit-evidence">{job.evidence || 'No sponsorship wording found. Not a guarantee; check before applying.'}</blockquote>
    <div className="fit-actions">
      <a className="button primary" href={job.source_url} target="_blank" rel="noreferrer" onClick={() => onOpen(job)}>Open listing <ExternalLink size={13} /></a>
      {job.application_status === 'Applied'
        ? <span className="signal signal-positive fit-status">Applied</span>
        : <button className="button secondary" onClick={() => onApplied(job)}>Mark applied</button>}
    </div>
    <p className="fit-keys"><kbd>j</kbd> <kbd>k</kbd> move · <kbd>Enter</kbd> open · <kbd>a</kbd> applied · <kbd>Esc</kbd> collapse</p>
  </aside>;
}
