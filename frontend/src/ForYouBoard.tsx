import { Search } from 'lucide-react';
import { lowFit, postedLabel, whyTags } from './forYou';
import { seniorityLabels, sponsorshipLabels, toggleItem, type Filters, type Job } from './types';

type Props = {
  jobs: Job[];
  total: number;
  page: number;
  perPage: number;
  loading: boolean;
  filters: Filters;
  update: (key: string, value: string) => void;
  goToPage: (page: number) => void;
};

const selects: [string, string, string[][]][] = [
  ['days', 'Posted', [['all', 'Any time'], ['7', 'Past 7 days'], ['14', 'Past 14 days'], ['30', 'Past 30 days']]],
  ['min_fit', 'Fit', [['', 'Any fit'], ['40', '40 and up'], ['60', '60 and up'], ['80', '80 and up']]],
  ['application_status', 'Status', [['open', 'Open work'], ['unapplied', 'Not applied'], ['New', 'New'], ['Opened', 'Opened'], ['Applied', 'Applied'], ['Skipped', 'Skipped'], ['any', 'All']]],
  ['sort', 'Sort', [['fit', 'Best fit'], ['newest', 'Newest posted'], ['fit_only', 'Fit only']]],
];
const shownTags = 3;

export function ForYouBoard({ jobs, total, page, perPage, loading, filters, update, goToPage }: Props) {
  const pageCount = Math.max(1, Math.ceil(total / perPage));
  const signals = filters.sponsorship ? filters.sponsorship.split(',') : [];
  const excluded = filters.hide ? filters.hide.split(',') : [];
  const unscored = total > 0 && jobs.length > 0 && jobs.every(job => job.fit_score === null);

  return <>
    <div className="queue-header"><div><h2>Ranked for you</h2><span>{loading ? 'Refreshing results…' : total > perPage ? `${total} roles ranked · showing ${(page - 1) * perPage + 1}–${Math.min(page * perPage, total)}` : `${total} roles ranked`}</span></div><span className="notice">Best match to your resume first; newer jobs win close calls.</span></div>
    <div className="toolbar">
      <label className="search"><Search size={16} /><input value={filters.query} onChange={event => update('query', event.target.value)} placeholder="Search title, institution, or location" /></label>
      <div className="filters">
        {selects.map(([key, label, values]) => <label key={key}><span>{label}</span><select value={filters[key]} onChange={event => update(key, event.target.value)}>{values.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>)}
      </div>
    </div>
    <div className="query-filter"><span>Sponsorship</span><button className={signals.length ? '' : 'selected'} onClick={() => update('sponsorship', '')}>All signals</button>{sponsorshipLabels.map(([status, label]) => <button key={status} aria-pressed={signals.includes(status)} className={signals.includes(status) ? 'selected' : ''} onClick={() => update('sponsorship', toggleItem(signals, status))}>{label}</button>)}</div>
    <div className="query-filter"><span>Exclude roles</span><button className={excluded.length ? '' : 'selected'} onClick={() => update('hide', '')}>None</button>{seniorityLabels.map(label => <button key={label} aria-pressed={excluded.includes(label)} className={excluded.includes(label) ? 'selected' : ''} onClick={() => update('hide', toggleItem(excluded, label))}>{label}</button>)}</div>
    {unscored && <p className="fit-notice" role="status">Add your resume at data/resume.json to rank jobs.</p>}
    <div className="table-scroll"><table className="fit-table"><thead><tr><th>Fit</th><th>Role</th><th>Why</th><th>Posted</th></tr></thead><tbody>{jobs.map(job => {
      const tags = whyTags(job);
      return <tr key={job.id} className={job.fit_score !== null && job.fit_score < lowFit ? 'low-fit' : ''}>
        <td className="fit-cell"><b>{job.fit_score ?? '–'}</b><span className="fit-meter" aria-hidden="true"><i style={{ width: `${job.fit_score ?? 0}%` }} /></span></td>
        <td className="role"><strong>{job.title || 'Untitled listing'}</strong><span>{[job.institution, job.location].filter(Boolean).join(' · ') || 'Institution unavailable'}</span></td>
        <td><span className="fit-tags">{tags.slice(0, shownTags).map(tag => <span key={tag.tone + tag.label} className={'fit-tag fit-' + tag.tone}>{tag.label}</span>)}{tags.length > shownTags && <span className="fit-tag">+{tags.length - shownTags}</span>}</span></td>
        <td className="date"><span>{postedLabel(job.age_days)}</span></td>
      </tr>;
    })}</tbody></table>
      {!loading && total === 0 && <div className="empty"><b>No jobs match these filters.</b><span>Clear a filter or widen the posted window.</span></div>}
      {pageCount > 1 && <nav className="pager" aria-label="Results pages"><span>Page {page} of {pageCount}</span><div><button className="button secondary" disabled={page <= 1 || loading} onClick={() => goToPage(page - 1)}>Previous</button><button className="button secondary" disabled={page >= pageCount || loading} onClick={() => goToPage(page + 1)}>Next</button></div></nav>}
    </div>
  </>;
}
