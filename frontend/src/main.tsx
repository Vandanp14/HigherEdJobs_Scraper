import { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bookmark, ChevronDown, ExternalLink, History, LayoutList, Play, RefreshCw, Search, Settings2 } from 'lucide-react';
import './index.css';

type Job = { id:number; title:string; institution:string; location:string; posted_date:string; search_groups:string; sponsorship_status:string; confidence:string; evidence:string; evidence_context:string; application_status:string; higheredjobs_url:string; apply_url:string; description_status:string };
type Group = { id:string; name:string; query:string; enabled:boolean };
type Filters = Record<string, string>;

const request = async (path:string, init?:RequestInit) => { const response = await fetch('/api' + path, init); if (!response.ok) throw new Error(await response.text()); return response.json(); };
const signalClass = (signal:string) => ({ 'Not Worth It':'signal-stop', 'Likely No Sponsorship':'signal-caution', 'Unsure - Review':'signal-review', 'Sponsorship Possible':'signal-positive', 'No Mention Found':'signal-empty' }[signal] || 'signal-empty');

function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [filters, setFilters] = useState<Filters>({ query:'', group:'', sponsorship:'', application_status:'', days:'7', sort:'newest' });
  const parameters = useMemo(() => new URLSearchParams(filters).toString(), [filters]);
  const update = (key:string, value:string) => setFilters(current => ({ ...current, [key]:value }));
  const load = async () => { setLoading(true); try { const [data, sourceGroups] = await Promise.all([request('/jobs?' + parameters), request('/groups')]); setJobs(data.items); setTotal(data.total); setGroups(sourceGroups); } finally { setLoading(false); } };
  useEffect(() => { const timer = window.setTimeout(load, 180); return () => window.clearTimeout(timer); }, [parameters]);
  const run = async () => { setLoading(true); try { await request('/runs', { method:'POST', headers:{ 'content-type':'application/json' }, body:'{}' }); await load(); } catch (error) { alert((error as Error).message); } finally { setLoading(false); } };
  const updateStatus = async (id:number, application_status:string) => { await request('/jobs/' + id, { method:'PATCH', headers:{ 'content-type':'application/json' }, body:JSON.stringify({ application_status }) }); load(); };
  const opened = (id:number) => request('/jobs/' + id + '/opened', { method:'POST' }).then(load);
  const selectedGroups = filters.group ? filters.group.split(',') : [];
  const toggleGroup = (id:string) => update('group', selectedGroups.includes(id) ? selectedGroups.filter(item => item !== id).join(',') : [...selectedGroups, id].join(','));
  const options:[string, string[][]][] = [
    ['days', [['0','Today'],['3','Past 3 days'],['7','Past 7 days'],['14','Past 14 days'],['30','Past 30 days'],['all','All time']]],
    ['sponsorship', [['','All sponsorship signals'],['Not Worth It','Not worth it'],['Likely No Sponsorship','Likely no sponsorship'],['Unsure - Review','Review needed'],['No Mention Found','No mention found'],['Sponsorship Possible','Sponsorship possible']]],
    ['application_status', [['','Open work'],['New','New'],['Opened','Opened'],['Applied','Applied'],['Skipped','Skipped']]],
    ['sort', [['newest','Newest posted'],['oldest','Oldest posted'],['first_seen','First seen'],['institution','Institution'],['title','Job title'],['state','State']]],
  ];

  return <div className="workspace">
    <aside className="sidebar"><div className="brand"><span>HEJ</span><div><b>HigherEdJobs</b><small>Review workspace</small></div></div><nav><a className="active"><LayoutList size={17}/> Job queue</a><a><Bookmark size={17}/> Saved views</a><a><History size={17}/> Run history</a></nav><div className="sidebar-bottom"><button onClick={() => setShowSources(!showSources)}><Settings2 size={16}/> Search sources</button><small>Local workspace<br/>Your data stays on this device.</small></div></aside>
    <main className="content"><header className="topbar"><div><p className="breadcrumb">JOB QUEUE / ALL ACTIVE ROLES</p><h1>Job review queue</h1><p>Prioritize roles, inspect sponsorship wording, and track your next step.</p></div><div className="header-actions"><button className="button secondary" onClick={() => request('/reanalyze', { method:'POST' }).then(load)}><RefreshCw size={15}/> Re-analyze</button><button className="button primary" disabled={loading} onClick={run}><Play size={14} fill="currentColor"/> Run enabled searches</button></div></header>
      {showSources && <section className="sources"><div className="section-title"><div><h2>Search sources</h2><p>Enable the keyword groups you want to include in the next run.</p></div><button className="icon-button" aria-label="Close search sources" onClick={() => setShowSources(false)}>×</button></div><div className="source-grid">{groups.map(group => <label key={group.id} className="source"><input type="checkbox" checked={group.enabled} onChange={async event => { await request('/groups/' + group.id, { method:'PATCH', headers:{ 'content-type':'application/json' }, body:JSON.stringify({ enabled:event.target.checked }) }); load(); }}/><span><b>{group.name}</b><small>{group.query}</small></span></label>)}</div></section>}
      <section className="queue"><div className="queue-header"><div><h2>All active roles</h2><span>{loading ? 'Refreshing results…' : `${total} roles in this view`}</span></div><span className="notice">Open source wording before making a decision.</span></div><div className="toolbar"><label className="search"><Search size={16}/><input value={filters.query} onChange={event => update('query', event.target.value)} placeholder="Search title, institution, or location"/></label><div className="filters">{options.map(([key, values]) => <label key={key}><span>{key === 'days' ? 'Date' : key === 'sponsorship' ? 'Sponsorship' : key === 'application_status' ? 'Status' : 'Sort'}</span><select value={filters[key]} onChange={event => update(key, event.target.value)}>{values.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>)}</div></div><div className="query-filter"><span>Query filter</span><button className={selectedGroups.length ? '' : 'selected'} onClick={() => update('group','')}>All queries</button>{groups.map(group => <button key={group.id} className={selectedGroups.includes(group.id) ? 'selected' : ''} onClick={() => toggleGroup(group.id)}>{group.name}</button>)}</div><div className="table-scroll"><table><thead><tr><th className="role-col">Role</th><th>Location</th><th>Posted</th><th>Search source</th><th>Sponsorship</th><th className="evidence-col">Evidence</th><th>Progress</th><th>Links</th></tr></thead><tbody>{jobs.map(job => <>
        <tr key={job.id}><td className="role"><strong>{job.title || 'Untitled listing'}</strong><span>{job.institution || 'Institution unavailable'}</span></td><td>{job.location || '—'}</td><td className="date">{job.posted_date || '—'}</td><td className="source-cell">{job.search_groups || '—'}</td><td><span className={'signal ' + signalClass(job.sponsorship_status)}>{job.sponsorship_status}</span><small className="confidence">{job.confidence}</small></td><td className="evidence"><button onClick={() => setExpanded(expanded === job.id ? null : job.id)} title="Show full source context">{job.evidence || (job.description_status === 'Pending' ? 'Description pending' : 'No relevant wording found')}<ChevronDown size={14}/></button></td><td><select className="status-select" value={job.application_status} onChange={event => updateStatus(job.id, event.target.value)}><option>New</option><option>Opened</option><option>Applied</option><option>Skipped</option></select></td><td className="link-cell"><a onClick={() => opened(job.id)} href={job.higheredjobs_url} target="_blank" rel="noreferrer">Listing <ExternalLink size={12}/></a>{job.apply_url && <a onClick={() => opened(job.id)} href={job.apply_url} target="_blank" rel="noreferrer">Apply <ExternalLink size={12}/></a>}</td></tr>
        {expanded === job.id && <tr key={'detail-' + job.id} className="detail"><td colSpan={8}><b>Source context</b><p>{job.evidence_context || 'No source context was captured for this listing.'}</p></td></tr>}
      </>)}</tbody></table>{!loading && jobs.length === 0 && <div className="empty"><b>No jobs in this view.</b><span>Run enabled searches or broaden the filters.</span></div>}</div></section>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App/>);
