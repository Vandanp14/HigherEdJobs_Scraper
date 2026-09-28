import { useEffect, useMemo, useState } from 'react';
import { Bookmark, ChevronDown, ExternalLink, History, LayoutList, LoaderCircle, Play, RefreshCw, Search, Settings2 } from 'lucide-react';
import { createRoot } from 'react-dom/client';
import './index.css';

type Job = {
  id: number;
  source: string;
  source_url: string;
  title: string | null;
  institution: string | null;
  location: string | null;
  salary: string | null;
  posted_date: string | null;
  application_due_date: string | null;
  search_groups: string | null;
  sponsorship_status: string;
  confidence: string;
  evidence: string | null;
  evidence_context: string | null;
  normalized_description: string | null;
  application_status: string;
  apply_url: string | null;
  description_status: string;
};
type Group = { id: string; name: string; query: string; enabled: boolean };
type Source = { id: string; name: string; description: string; supports_queries: boolean };
type Filters = Record<string, string>;
type Run = {
  source: string;
  completed_at: string | null;
  jobs_discovered: number;
  new_jobs: number;
  updated_jobs: number;
  errors: { source?: string; group?: string; listing_url?: string; error: string }[];
};

const request = async (path: string, init?: RequestInit) => {
  const response = await fetch('/api' + path, init);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};
const signalClass = (signal: string) => ({
  'Not Worth It': 'signal-stop',
  'Likely No Sponsorship': 'signal-caution',
  'Unsure - Review': 'signal-review',
  'Sponsorship Possible': 'signal-positive',
  'No Mention Found': 'signal-empty',
}[signal] || 'signal-empty');

function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [activeRun, setActiveRun] = useState<'higheredjobs' | 'air' | 'reanalyze' | null>(null);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [notice, setNotice] = useState('');
  const [filters, setFilters] = useState<Filters>({
    query: '', group: '', sponsorship: '', description: '', application_status: '', days: '7', sort: 'newest', source: '',
  });
  const parameters = useMemo(() => new URLSearchParams(filters).toString(), [filters]);
  const update = (key: string, value: string) => setFilters(current => ({ ...current, [key]: value }));
  const sourceFilter = filters.source;
  const selectedGroups = filters.group ? filters.group.split(',') : [];

  const load = async () => {
    setLoading(true);
    try {
      const [data, sourceGroups, sourceList] = await Promise.all([
        request('/jobs?' + parameters),
        request('/groups'),
        request('/sources'),
      ]);
      setJobs(data.items);
      setTotal(data.total);
      setGroups(sourceGroups);
      setSources(sourceList);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    const timer = window.setTimeout(load, 180);
    return () => window.clearTimeout(timer);
  }, [parameters]);
  useEffect(() => {
    if (!activeRun || !runStartedAt) return undefined;
    const updateElapsed = () => setElapsedSeconds(Math.floor((Date.now() - runStartedAt) / 1000));
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [activeRun, runStartedAt]);

  const beginRun = (run: 'higheredjobs' | 'air' | 'reanalyze') => {
    setActiveRun(run);
    setRunStartedAt(Date.now());
    setElapsedSeconds(0);
  };
  const finishRun = () => {
    setActiveRun(null);
    setRunStartedAt(null);
  };
  const elapsedLabel = `${Math.floor(elapsedSeconds / 60)}m ${String(elapsedSeconds % 60).padStart(2, '0')}s`;

  const runHigherEdJobs = async () => {
    if (activeRun) return;
    beginRun('higheredjobs');
    setLoading(true);
    setNotice('HigherEdJobs search is running. Keep this tab open; do not refresh it.');
    try {
      const result = await request('/runs', {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}',
      }) as Run;
      const errors = result.errors?.length ? ` ${result.errors.length} group(s) failed.` : '';
      setNotice(`HigherEdJobs run complete: ${result.jobs_discovered} listings found (${result.new_jobs} new, ${result.updated_jobs} updated).${errors}`);
      await load();
    } catch (error) {
      setNotice(`HigherEdJobs run failed: ${(error as Error).message}`);
    } finally {
      setLoading(false);
      finishRun();
    }
  };
  const runAir = async () => {
    if (activeRun) return;
    beginRun('air');
    setLoading(true);
    setNotice('AIR Career Center refresh is running. Keep this tab open; do not refresh it.');
    try {
      const result = await request('/runs/air', { method: 'POST' }) as Run;
      const errors = result.errors?.length ? ` ${result.errors.length} description(s) failed; rows were retained.` : '';
      setNotice(`AIR run complete: ${result.jobs_discovered} listings found (${result.new_jobs} new, ${result.updated_jobs} updated).${errors}`);
      await load();
    } catch (error) {
      setNotice(`AIR run failed: ${(error as Error).message}`);
    } finally {
      setLoading(false);
      finishRun();
    }
  };
  const reanalyze = async () => {
    if (activeRun) return;
    beginRun('reanalyze');
    setLoading(true);
    try {
      const result = await request('/reanalyze', { method: 'POST' }) as { reanalyzed: number };
      setNotice(`Re-analyzed ${result.reanalyzed} saved descriptions. No new search was run.`);
      await load();
    } catch (error) {
      setNotice(`Re-analysis failed: ${(error as Error).message}`);
    } finally {
      setLoading(false);
      finishRun();
    }
  };
  const updateStatus = async (id: number, application_status: string) => {
    await request('/jobs/' + id, {
      method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ application_status }),
    });
    load();
  };
  const opened = (id: number) => request('/jobs/' + id + '/opened', { method: 'POST' }).then(load);
  const toggleGroup = (id: string) => update('group', selectedGroups.includes(id)
    ? selectedGroups.filter(item => item !== id).join(',')
    : [...selectedGroups, id].join(','));
  const options: [string, string[][]][] = [
    ['days', [['0', 'Today'], ['3', 'Past 3 days'], ['7', 'Past 7 days'], ['14', 'Past 14 days'], ['30', 'Past 30 days'], ['all', 'All time']]],
    ['sponsorship', [['', 'All sponsorship signals'], ['Not Worth It', 'Not worth it'], ['Likely No Sponsorship', 'Likely no sponsorship'], ['Unsure - Review', 'Review needed'], ['No Mention Found', 'No mention found'], ['Sponsorship Possible', 'Sponsorship possible']]],
    ['description', [['complete', 'Complete only'], ['', 'Any description state'], ['missing', 'Missing description'], ['failed', 'Failed to capture']]],
    ['application_status', [['', 'Open work'], ['New', 'New'], ['Opened', 'Opened'], ['Applied', 'Applied'], ['Skipped', 'Skipped']]],
    ['sort', [['newest', 'Newest posted'], ['oldest', 'Oldest posted'], ['first_seen', 'First seen'], ['institution', 'Institution'], ['title', 'Job title'], ['state', 'State']]],
  ];

  return <div className="workspace">
    <aside className="sidebar">
      <div className="brand"><span>HEJ</span><div><b>HigherEdJobs</b><small>Review workspace</small></div></div>
      <nav><a className="active"><LayoutList size={17} /> Job queue</a><a><Bookmark size={17} /> Saved views</a><a><History size={17} /> Run history</a></nav>
      <div className="sidebar-bottom"><button onClick={() => setShowSources(!showSources)}><Settings2 size={16} /> Search sources</button><small>Local workspace<br />Your data stays on this device.</small></div>
    </aside>
    <main className="content">
      <header className="topbar">
        <div><p className="breadcrumb">JOB QUEUE / ALL ACTIVE ROLES</p><h1>Job review queue</h1><p>Prioritize roles, inspect sponsorship wording, and track your next step.</p></div>
        <div className="header-actions">
          <button className="button secondary" disabled={Boolean(activeRun)} onClick={reanalyze}>{activeRun === 'reanalyze' ? <LoaderCircle className="animate-spin" size={15} /> : <RefreshCw size={15} />} {activeRun === 'reanalyze' ? `Re-analyzing · ${elapsedLabel}` : 'Re-analyze saved jobs'}</button>
          <button className="button secondary air-button" disabled={Boolean(activeRun)} onClick={runAir}>{activeRun === 'air' ? <LoaderCircle className="animate-spin" size={14} /> : <Play size={14} fill="currentColor" />} {activeRun === 'air' ? `Refreshing · ${elapsedLabel}` : 'Run AIR Career Center'}</button>
          <button className="button primary" disabled={Boolean(activeRun)} onClick={runHigherEdJobs}>{activeRun === 'higheredjobs' ? <LoaderCircle className="animate-spin" size={14} /> : <Play size={14} fill="currentColor" />} {activeRun === 'higheredjobs' ? `Searching · ${elapsedLabel}` : 'Run HigherEdJobs'}</button>
        </div>
      </header>
      {notice && <p className="run-notice" role="status">{notice}</p>}
      {activeRun && <p className="run-progress" role="status"><LoaderCircle className="animate-spin" size={15} /><span><b>{activeRun === 'higheredjobs' ? 'HigherEdJobs search' : activeRun === 'air' ? 'AIR refresh' : 'Description re-analysis'} in progress</b><small>Elapsed {elapsedLabel}. Keep this tab open; do not refresh while it runs.</small></span></p>}
      {showSources && <section className="sources">
        <div className="section-title"><div><h2>Search sources</h2><p>Run AIR independently or enable the keyword groups used by HigherEdJobs.</p></div><button className="icon-button" aria-label="Close search sources" onClick={() => setShowSources(false)}>×</button></div>
        <div className="source-grid">
          {sources.map(source => <div key={source.id} className="source source-info"><b>{source.name}</b><small>{source.description}</small><button className="source-run" onClick={source.id === 'air' ? runAir : runHigherEdJobs} disabled={Boolean(activeRun)}>{activeRun === source.id ? `Running · ${elapsedLabel}` : 'Run source'}</button></div>)}
          {groups.map(group => <label key={group.id} className="source"><input type="checkbox" checked={group.enabled} onChange={async event => { await request('/groups/' + group.id, { method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ enabled: event.target.checked }) }); load(); }} /><span><b>{group.name}</b><small>{group.query}</small></span></label>)}
        </div>
      </section>}
      <section className="queue">
        <div className="queue-header"><div><h2>Unified job queue</h2><span>{loading ? 'Refreshing results…' : `${total} roles in this view`}</span></div><span className="notice">Open source wording before making a decision.</span></div>
        <div className="toolbar">
          <label className="search"><Search size={16} /><input value={filters.query} onChange={event => update('query', event.target.value)} placeholder="Search title, institution, or location" /></label>
          <div className="filters">
            <label><span>Source</span><select value={sourceFilter} onChange={event => { update('source', event.target.value); if (event.target.value === 'air') update('group', ''); }}><option value="">All sources</option><option value="higheredjobs">HigherEdJobs</option><option value="air">AIR Career Center</option></select></label>
            {options.map(([key, values]) => <label key={key}><span>{key === 'days' ? 'Date' : key === 'sponsorship' ? 'Sponsorship' : key === 'description' ? 'Description' : key === 'application_status' ? 'Status' : 'Sort'}</span><select value={filters[key]} onChange={event => update(key, event.target.value)}>{values.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>)}
          </div>
        </div>
        {sourceFilter !== 'air' && <div className="query-filter"><span>Query filter</span><button className={selectedGroups.length ? '' : 'selected'} onClick={() => update('group', '')}>All queries</button>{groups.map(group => <button key={group.id} className={selectedGroups.includes(group.id) ? 'selected' : ''} onClick={() => toggleGroup(group.id)}>{group.name}</button>)}</div>}
        <div className="table-scroll"><table><thead><tr><th className="role-col">Role</th><th>Source</th><th>Location</th><th>Salary</th><th>Posted / Due</th><th>Sponsorship</th><th className="evidence-col">Evidence</th><th>Progress</th><th>Links</th></tr></thead><tbody>{jobs.map(job => <>{<tr key={job.id}>
          <td className="role"><strong>{job.title || 'Untitled listing'}</strong><span>{job.institution || 'Institution unavailable'}</span></td>
          <td><span className={'source-badge source-' + job.source}>{job.source === 'air' ? 'AIR' : 'HigherEdJobs'}</span>{job.search_groups && <small className="source-meta">{job.search_groups}</small>}</td>
          <td>{job.location || '—'}</td><td>{job.salary || '—'}</td>
          <td className="date">{job.source === 'air' ? <><span>Due {job.application_due_date || '—'}</span></> : <>Posted {job.posted_date || '—'}</>}</td>
          <td><span className={'signal ' + signalClass(job.sponsorship_status)}>{job.sponsorship_status}</span><small className="confidence">{job.confidence}</small></td>
          <td className="evidence"><button aria-controls={'description-' + job.id} aria-expanded={expanded === job.id} onClick={() => setExpanded(expanded === job.id ? null : job.id)}>{job.description_status === 'Failed' ? 'Description failed' : job.evidence || (job.description_status === 'Pending' ? 'Description pending' : 'View description')}<ChevronDown size={14} /></button></td>
          <td><select className="status-select" value={job.application_status} onChange={event => updateStatus(job.id, event.target.value)}><option>New</option><option>Opened</option><option>Applied</option><option>Skipped</option></select></td>
          <td className="link-cell"><a onClick={() => opened(job.id)} href={job.source_url} target="_blank" rel="noreferrer">Listing <ExternalLink size={12} /></a>{job.apply_url && <a onClick={() => opened(job.id)} href={job.apply_url} target="_blank" rel="noreferrer">Apply <ExternalLink size={12} /></a>}</td>
        </tr>}{expanded === job.id && <tr key={'detail-' + job.id} className="detail" id={'description-' + job.id}><td colSpan={9}><section className="context"><b>{job.description_status === 'Failed' ? 'Description unavailable' : 'Classification context'}</b><p>{job.description_status === 'Failed' ? 'The detail page could not be captured on the last run. This is not the same as no sponsorship mention.' : job.evidence_context || 'No sponsorship-specific wording was found in this listing.'}</p></section><details className="full-description"><summary>Full job description</summary><p>{job.normalized_description || 'The description has not been captured yet. Open the listing or run the source again to refresh it.'}</p></details></td></tr>}</>)}</tbody></table>{!loading && jobs.length === 0 && <div className="empty"><b>No jobs in this view.</b><span>Run a source or broaden the filters.</span></div>}</div>
      </section>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App />);
