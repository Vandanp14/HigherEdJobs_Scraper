import { useEffect, useMemo, useState, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertTriangle,
  Bookmark,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  ExternalLink,
  Filter,
  HelpCircle,
  History,
  LayoutList,
  MapPin,
  MessageSquare,
  MinusCircle,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  Sparkles,
  X,
  XCircle,
} from 'lucide-react';
import './index.css';

type Job = {
  id: number;
  title: string;
  institution: string;
  location: string;
  city?: string;
  state?: string;
  salary?: string;
  posted_date: string;
  first_seen_at?: string;
  search_groups: string;
  sponsorship_status: string;
  confidence: string;
  evidence: string;
  evidence_context: string;
  matched_terms?: string[];
  application_status: string;
  notes?: string;
  higheredjobs_url: string;
  apply_url: string;
  description_status: string;
};

type Group = { id: string; name: string; query: string; enabled: boolean };
type Filters = {
  query: string;
  group: string;
  sponsorship: string;
  application_status: string;
  days: string;
  sort: string;
};

type Toast = { id: number; message: string; type: 'info' | 'success' | 'error' };

const request = async (path: string, init?: RequestInit) => {
  const response = await fetch('/api' + path, init);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};

function SignalBadge({ status, confidence }: { status: string; confidence?: string }) {
  let Icon = MinusCircle;
  let badgeClass = 'signal-empty';

  if (status === 'Sponsorship Possible') {
    Icon = CheckCircle2;
    badgeClass = 'signal-positive';
  } else if (status === 'Unsure - Review') {
    Icon = HelpCircle;
    badgeClass = 'signal-review';
  } else if (status === 'Likely No Sponsorship') {
    Icon = AlertTriangle;
    badgeClass = 'signal-caution';
  } else if (status === 'Not Worth It') {
    Icon = XCircle;
    badgeClass = 'signal-stop';
  }

  return (
    <div className="signal-wrapper">
      <span className={`signal ${badgeClass}`}>
        <Icon size={12} className="signal-icon" />
        <span>{status}</span>
      </span>
      {confidence && confidence !== '-' && (
        <small className="confidence">{confidence} confidence</small>
      )}
    </div>
  );
}

function HighlightedText({ text, terms }: { text: string; terms?: string[] }) {
  if (!text) return <span className="empty-text">No source context captured for this listing.</span>;

  const keywords = Array.from(
    new Set(
      [
        ...(terms || []),
        'sponsorship',
        'sponsor',
        'visa',
        'h-1b',
        'h1b',
        'citizen',
        'citizenship',
        'permanent resident',
        'green card',
        'opt',
        'cpt',
        'relocation',
      ].filter(Boolean)
    )
  );

  if (!keywords.length) return <span>{text}</span>;

  const escaped = keywords.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = text.split(pattern);

  return (
    <>
      {parts.map((part, i) =>
        keywords.some(k => k.toLowerCase() === part.toLowerCase()) ? (
          <mark key={i} className="kw-highlight">
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </>
  );
}

function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [notesState, setNotesState] = useState<Record<number, string>>({});
  const [savingNotesId, setSavingNotesId] = useState<number | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);

  const [filters, setFilters] = useState<Filters>({
    query: '',
    group: '',
    sponsorship: '',
    application_status: '',
    days: '7',
    sort: 'newest',
  });

  const showToast = (message: string, type: 'info' | 'success' | 'error' = 'info') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3200);
  };

  const parameters = useMemo(() => {
    const params = new URLSearchParams(filters);
    params.set('page', page.toString());
    return params.toString();
  }, [filters, page]);

  const updateFilter = (key: keyof Filters, value: string) => {
    setFilters(current => ({ ...current, [key]: value }));
    setPage(1);
  };

  const resetFilters = () => {
    setFilters({
      query: '',
      group: '',
      sponsorship: '',
      application_status: '',
      days: '7',
      sort: 'newest',
    });
    setPage(1);
    showToast('Filters reset to default', 'info');
  };

  const load = async () => {
    setLoading(true);
    try {
      const [data, sourceGroups] = await Promise.all([
        request('/jobs?' + parameters),
        request('/groups'),
      ]);
      setJobs(data.items);
      setTotal(data.total);
      setGroups(sourceGroups);

      // Initialize notes state
      const initialNotes: Record<number, string> = {};
      data.items.forEach((j: Job) => {
        initialNotes[j.id] = j.notes || '';
      });
      setNotesState(prev => ({ ...initialNotes, ...prev }));
    } catch (err) {
      showToast((err as Error).message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(load, 180);
    return () => window.clearTimeout(timer);
  }, [parameters]);

  // Shortcut key '/' or 'Cmd+K' to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        (e.key === '/' || (e.key === 'k' && (e.metaKey || e.ctrlKey))) &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA' &&
        document.activeElement?.tagName !== 'SELECT'
      ) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const runSearches = async () => {
    setLoading(true);
    try {
      await request('/runs', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: '{}',
      });
      showToast('Search run completed successfully!', 'success');
      await load();
    } catch (error) {
      showToast((error as Error).message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleReanalyze = async () => {
    setReanalyzing(true);
    try {
      const res = await request('/reanalyze', { method: 'POST' });
      showToast(`Re-analyzed ${res.reanalyzed} listings`, 'success');
      await load();
    } catch (err) {
      showToast((err as Error).message, 'error');
    } finally {
      setReanalyzing(false);
    }
  };

  const updateStatus = async (id: number, application_status: string) => {
    try {
      await request('/jobs/' + id, {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ application_status }),
      });
      showToast(`Status updated to "${application_status}"`, 'success');
      load();
    } catch (err) {
      showToast((err as Error).message, 'error');
    }
  };

  const saveNotes = async (id: number) => {
    setSavingNotesId(id);
    try {
      await request('/jobs/' + id, {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ notes: notesState[id] || '' }),
      });
      showToast('Notes saved', 'success');
      load();
    } catch (err) {
      showToast((err as Error).message, 'error');
    } finally {
      setSavingNotesId(null);
    }
  };

  const markOpened = (id: number) => {
    request('/jobs/' + id + '/opened', { method: 'POST' }).then(load);
  };

  const copyWording = (id: number, text: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    showToast('Evidence wording copied to clipboard', 'info');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const selectedGroups = filters.group ? filters.group.split(',').filter(Boolean) : [];
  const toggleGroup = (id: string) => {
    const next = selectedGroups.includes(id)
      ? selectedGroups.filter(item => item !== id)
      : [...selectedGroups, id];
    updateFilter('group', next.join(','));
  };

  const toggleAllSources = async (enable: boolean) => {
    setLoading(true);
    try {
      await Promise.all(
        groups.map(g =>
          request('/groups/' + g.id, {
            method: 'PATCH',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ enabled: enable }),
          })
        )
      );
      showToast(enable ? 'All sources enabled' : 'All sources disabled', 'info');
      await load();
    } catch (err) {
      showToast((err as Error).message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Metric counts from loaded jobs
  const metrics = useMemo(() => {
    const possible = jobs.filter(j => j.sponsorship_status === 'Sponsorship Possible').length;
    const review = jobs.filter(j => j.sponsorship_status === 'Unsure - Review').length;
    const likelyNo = jobs.filter(j => j.sponsorship_status === 'Likely No Sponsorship' || j.sponsorship_status === 'Not Worth It').length;
    const applied = jobs.filter(j => j.application_status === 'Applied').length;
    return { possible, review, likelyNo, applied };
  }, [jobs]);

  const hasActiveFilters = Boolean(
    filters.query ||
      filters.group ||
      filters.sponsorship ||
      filters.application_status ||
      filters.days !== '7' ||
      filters.sort !== 'newest'
  );

  const options: [keyof Filters, string, string[][]][] = [
    [
      'days',
      'Date range',
      [
        ['0', 'Today'],
        ['3', 'Past 3 days'],
        ['7', 'Past 7 days'],
        ['14', 'Past 14 days'],
        ['30', 'Past 30 days'],
        ['all', 'All time'],
      ],
    ],
    [
      'sponsorship',
      'Sponsorship',
      [
        ['', 'All signals'],
        ['Sponsorship Possible', 'Sponsorship possible'],
        ['Unsure - Review', 'Review needed'],
        ['Likely No Sponsorship', 'Likely no sponsorship'],
        ['Not Worth It', 'Not worth it'],
        ['No Mention Found', 'No mention found'],
      ],
    ],
    [
      'application_status',
      'Status',
      [
        ['', 'Open work'],
        ['New', 'New'],
        ['Opened', 'Opened'],
        ['Applied', 'Applied'],
        ['Skipped', 'Skipped'],
      ],
    ],
    [
      'sort',
      'Sort by',
      [
        ['newest', 'Newest posted'],
        ['oldest', 'Oldest posted'],
        ['first_seen', 'First seen'],
        ['institution', 'Institution'],
        ['title', 'Job title'],
        ['state', 'State'],
      ],
    ],
  ];

  const totalPages = Math.max(1, Math.ceil(total / 50));

  return (
    <div className="workspace">
      {/* Toast Notifications */}
      <div className="toast-container">
        {toasts.map(toast => (
          <div key={toast.id} className={`toast toast-${toast.type}`}>
            {toast.type === 'success' && <CheckCircle2 size={16} />}
            {toast.type === 'error' && <AlertTriangle size={16} />}
            {toast.type === 'info' && <Sparkles size={16} />}
            <span>{toast.message}</span>
          </div>
        ))}
      </div>

      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="brand">
          <span>HEJ</span>
          <div>
            <b>HigherEdJobs</b>
            <small>Review workspace</small>
          </div>
        </div>
        <nav>
          <a className="active" href="#queue">
            <LayoutList size={17} /> Job queue
          </a>
          <a
            href="#possible"
            onClick={e => {
              e.preventDefault();
              updateFilter('sponsorship', 'Sponsorship Possible');
            }}
          >
            <Bookmark size={17} /> Sponsorship Possible
          </a>
          <a
            href="#history"
            onClick={e => {
              e.preventDefault();
              setShowSources(true);
            }}
          >
            <History size={17} /> Manage Sources
          </a>
        </nav>
        <div className="sidebar-bottom">
          <button onClick={() => setShowSources(!showSources)} className={showSources ? 'active' : ''}>
            <Settings2 size={16} /> Search sources
          </button>
          <small>
            Local workspace
            <br />
            Your data stays on this device.
          </small>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="content">
        <header className="topbar">
          <div>
            <p className="breadcrumb">JOB QUEUE / ALL ACTIVE ROLES</p>
            <h1>Job review queue</h1>
            <p>Prioritize roles, inspect sponsorship wording, and track your next step.</p>
          </div>
          <div className="header-actions">
            <button
              className="button secondary"
              disabled={reanalyzing || loading}
              onClick={handleReanalyze}
              title="Re-run classifier over stored job descriptions"
            >
              <RefreshCw size={15} className={reanalyzing ? 'spin' : ''} />
              {reanalyzing ? 'Re-analyzing…' : 'Re-analyze'}
            </button>
            <button className="button primary" disabled={loading} onClick={runSearches}>
              <Play size={14} fill="currentColor" /> Run enabled searches
            </button>
          </div>
        </header>

        {/* Quick KPI Stats Summary Cards */}
        <section className="kpi-grid">
          <div
            className={`kpi-card ${filters.sponsorship === '' && !filters.application_status ? 'active' : ''}`}
            onClick={() => {
              updateFilter('sponsorship', '');
              updateFilter('application_status', '');
            }}
          >
            <div className="kpi-icon kpi-all">
              <LayoutList size={18} />
            </div>
            <div>
              <span className="kpi-value">{total}</span>
              <span className="kpi-label">Total in View</span>
            </div>
          </div>

          <div
            className={`kpi-card ${filters.sponsorship === 'Sponsorship Possible' ? 'active' : ''}`}
            onClick={() => updateFilter('sponsorship', filters.sponsorship === 'Sponsorship Possible' ? '' : 'Sponsorship Possible')}
          >
            <div className="kpi-icon kpi-positive">
              <CheckCircle2 size={18} />
            </div>
            <div>
              <span className="kpi-value">{metrics.possible}</span>
              <span className="kpi-label">Sponsorship Possible</span>
            </div>
          </div>

          <div
            className={`kpi-card ${filters.sponsorship === 'Unsure - Review' ? 'active' : ''}`}
            onClick={() => updateFilter('sponsorship', filters.sponsorship === 'Unsure - Review' ? '' : 'Unsure - Review')}
          >
            <div className="kpi-icon kpi-review">
              <HelpCircle size={18} />
            </div>
            <div>
              <span className="kpi-value">{metrics.review}</span>
              <span className="kpi-label">Review Needed</span>
            </div>
          </div>

          <div
            className={`kpi-card ${filters.application_status === 'Applied' ? 'active' : ''}`}
            onClick={() => updateFilter('application_status', filters.application_status === 'Applied' ? '' : 'Applied')}
          >
            <div className="kpi-icon kpi-applied">
              <Check size={18} />
            </div>
            <div>
              <span className="kpi-value">{metrics.applied}</span>
              <span className="kpi-label">Applied Roles</span>
            </div>
          </div>
        </section>

        {/* Search Sources Drawer */}
        {showSources && (
          <section className="sources">
            <div className="section-title">
              <div>
                <h2>Search sources</h2>
                <p>Enable or disable keyword groups to include in subsequent scraper runs.</p>
              </div>
              <div className="source-actions">
                <button className="button-link" onClick={() => toggleAllSources(true)}>
                  Enable all
                </button>
                <span className="dot">•</span>
                <button className="button-link" onClick={() => toggleAllSources(false)}>
                  Disable all
                </button>
                <button
                  className="icon-button"
                  aria-label="Close search sources"
                  onClick={() => setShowSources(false)}
                >
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="source-grid">
              {groups.map(group => (
                <label key={group.id} className="source">
                  <input
                    type="checkbox"
                    checked={group.enabled}
                    onChange={async event => {
                      await request('/groups/' + group.id, {
                        method: 'PATCH',
                        headers: { 'content-type': 'application/json' },
                        body: JSON.stringify({ enabled: event.target.checked }),
                      });
                      load();
                    }}
                  />
                  <span>
                    <b>{group.name}</b>
                    <small>{group.query}</small>
                  </span>
                </label>
              ))}
            </div>
          </section>
        )}

        {/* Main Job Queue Panel */}
        <section className="queue">
          <div className="queue-header">
            <div>
              <h2>All active roles</h2>
              <span>{loading ? 'Refreshing results…' : `${total} roles matching criteria`}</span>
            </div>
            <span className="notice">
              <Sparkles size={13} className="inline-icon" /> Inspect source wording before making decisions.
            </span>
          </div>

          {/* Search & Select Toolbar */}
          <div className="toolbar">
            <label className="search">
              <Search size={16} />
              <input
                ref={searchInputRef}
                value={filters.query}
                onChange={event => updateFilter('query', event.target.value)}
                placeholder="Search title, institution, location… (Press /)"
              />
              {filters.query ? (
                <button
                  className="search-clear"
                  onClick={() => updateFilter('query', '')}
                  title="Clear search"
                >
                  <X size={14} />
                </button>
              ) : (
                <kbd className="search-kbd">/</kbd>
              )}
            </label>

            <div className="filters">
              {options.map(([key, labelText, values]) => (
                <label key={key}>
                  <span>{labelText}</span>
                  <select
                    value={filters[key]}
                    onChange={event => updateFilter(key, event.target.value)}
                  >
                    {values.map(([value, optionLabel]) => (
                      <option key={value} value={value}>
                        {optionLabel}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </div>

          {/* Keyword Search Groups Filter */}
          <div className="query-filter">
            <span>Query filter</span>
            <button
              className={selectedGroups.length === 0 ? 'selected' : ''}
              onClick={() => updateFilter('group', '')}
            >
              All queries
            </button>
            {groups.map(group => (
              <button
                key={group.id}
                className={selectedGroups.includes(group.id) ? 'selected' : ''}
                onClick={() => toggleGroup(group.id)}
              >
                {group.name}
              </button>
            ))}
          </div>

          {/* Active Filter Tags */}
          {hasActiveFilters && (
            <div className="active-filters">
              <span className="active-filters-label">
                <Filter size={12} /> Active:
              </span>
              {filters.query && (
                <span className="filter-chip">
                  Search: "{filters.query}"
                  <button onClick={() => updateFilter('query', '')}>
                    <X size={12} />
                  </button>
                </span>
              )}
              {selectedGroups.length > 0 && (
                <span className="filter-chip">
                  Groups: {selectedGroups.length} selected
                  <button onClick={() => updateFilter('group', '')}>
                    <X size={12} />
                  </button>
                </span>
              )}
              {filters.sponsorship && (
                <span className="filter-chip">
                  Sponsorship: {filters.sponsorship}
                  <button onClick={() => updateFilter('sponsorship', '')}>
                    <X size={12} />
                  </button>
                </span>
              )}
              {filters.application_status && (
                <span className="filter-chip">
                  Status: {filters.application_status}
                  <button onClick={() => updateFilter('application_status', '')}>
                    <X size={12} />
                  </button>
                </span>
              )}
              {filters.days !== '7' && (
                <span className="filter-chip">
                  Date: {filters.days === 'all' ? 'All time' : `Past ${filters.days} days`}
                  <button onClick={() => updateFilter('days', '7')}>
                    <X size={12} />
                  </button>
                </span>
              )}
              {filters.sort !== 'newest' && (
                <span className="filter-chip">
                  Sort: {filters.sort}
                  <button onClick={() => updateFilter('sort', 'newest')}>
                    <X size={12} />
                  </button>
                </span>
              )}
              <button className="reset-all" onClick={resetFilters}>
                <RotateCcw size={12} /> Reset all
              </button>
            </div>
          )}

          {/* Job Results Table */}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th className="role-col">Role & Institution</th>
                  <th>Location</th>
                  <th>Posted</th>
                  <th>Search Source</th>
                  <th>Sponsorship</th>
                  <th className="evidence-col">Evidence Wording</th>
                  <th>Progress</th>
                  <th>Links</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <>
                    <tr key={job.id} className={expanded === job.id ? 'row-expanded' : ''}>
                      <td className="role">
                        <strong>{job.title || 'Untitled listing'}</strong>
                        <span>
                          <Building2 size={12} className="inline-icon" />
                          {job.institution || 'Institution unavailable'}
                        </span>
                      </td>
                      <td>
                        <span className="location-cell">
                          <MapPin size={12} className="inline-icon" />
                          {job.location || '—'}
                        </span>
                      </td>
                      <td className="date">
                        <Clock size={12} className="inline-icon" />
                        {job.posted_date || '—'}
                      </td>
                      <td className="source-cell">{job.search_groups || '—'}</td>
                      <td>
                        <SignalBadge
                          status={job.sponsorship_status}
                          confidence={job.confidence}
                        />
                      </td>
                      <td className="evidence">
                        <button
                          onClick={() => setExpanded(expanded === job.id ? null : job.id)}
                          title="Click to view full source context wording"
                          className="evidence-trigger"
                        >
                          <span className="evidence-preview">
                            {job.evidence ||
                              (job.description_status === 'Pending'
                                ? 'Description pending'
                                : 'No relevant wording found')}
                          </span>
                          <ChevronDown
                            size={14}
                            className={`chevron-icon ${expanded === job.id ? 'rotate-180' : ''}`}
                          />
                        </button>
                      </td>
                      <td>
                        <select
                          className={`status-select status-tag-${(job.application_status || 'New').toLowerCase()}`}
                          value={job.application_status}
                          onChange={event => updateStatus(job.id, event.target.value)}
                        >
                          <option value="New">New</option>
                          <option value="Opened">Opened</option>
                          <option value="Applied">Applied</option>
                          <option value="Skipped">Skipped</option>
                        </select>
                      </td>
                      <td className="link-cell">
                        <a
                          onClick={() => markOpened(job.id)}
                          href={job.higheredjobs_url}
                          target="_blank"
                          rel="noreferrer"
                          title="Open listing on HigherEdJobs"
                        >
                          Listing <ExternalLink size={12} />
                        </a>
                        {job.apply_url && (
                          <a
                            onClick={() => markOpened(job.id)}
                            href={job.apply_url}
                            target="_blank"
                            rel="noreferrer"
                            className="apply-link"
                            title="Direct institutional apply link"
                          >
                            Apply <ExternalLink size={12} />
                          </a>
                        )}
                      </td>
                    </tr>

                    {/* Expanded Detail View */}
                    {expanded === job.id && (
                      <tr key={'detail-' + job.id} className="detail-row">
                        <td colSpan={8}>
                          <div className="detail-card">
                            <div className="detail-header">
                              <div className="detail-title-group">
                                <b>Source Wording & Context</b>
                                <span className="matched-meta">
                                  {job.matched_terms && job.matched_terms.length > 0 && (
                                    <span>
                                      Matched terms: <strong>{job.matched_terms.join(', ')}</strong>
                                    </span>
                                  )}
                                </span>
                              </div>
                              <button
                                className="button secondary button-sm"
                                onClick={() => copyWording(job.id, job.evidence_context || job.evidence)}
                              >
                                {copiedId === job.id ? <Check size={13} /> : <Copy size={13} />}
                                {copiedId === job.id ? 'Copied!' : 'Copy wording'}
                              </button>
                            </div>

                            <div className="detail-body">
                              <p className="context-text">
                                <HighlightedText
                                  text={job.evidence_context || job.evidence}
                                  terms={job.matched_terms}
                                />
                              </p>
                            </div>

                            {/* Job Notes Area */}
                            <div className="detail-notes">
                              <label>
                                <MessageSquare size={13} />
                                <span>Personal Notes & Next Steps:</span>
                              </label>
                              <div className="notes-input-wrapper">
                                <textarea
                                  value={notesState[job.id] ?? ''}
                                  onChange={e =>
                                    setNotesState({ ...notesState, [job.id]: e.target.value })
                                  }
                                  placeholder="Add notes about salary, contact, interview dates, or sponsorship follow-up…"
                                  rows={2}
                                />
                                <button
                                  className="button secondary button-xs"
                                  disabled={savingNotesId === job.id}
                                  onClick={() => saveNotes(job.id)}
                                >
                                  {savingNotesId === job.id ? 'Saving…' : 'Save Notes'}
                                </button>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>

            {/* Empty State */}
            {!loading && jobs.length === 0 && (
              <div className="empty">
                <div className="empty-icon">
                  <Search size={32} />
                </div>
                <b>No job roles matched this view</b>
                <span>Try broadening your search query, sponsorship filters, or date range.</span>
                {hasActiveFilters && (
                  <button className="button secondary button-sm mt-3" onClick={resetFilters}>
                    <RotateCcw size={14} /> Clear all active filters
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Pagination Controls */}
          {total > 0 && (
            <div className="pagination">
              <span className="pagination-info">
                Showing <strong>{jobs.length > 0 ? (page - 1) * 50 + 1 : 0}</strong> -{' '}
                <strong>{Math.min(page * 50, total)}</strong> of <strong>{total}</strong> roles
              </span>
              <div className="pagination-buttons">
                <button
                  className="button secondary button-sm"
                  disabled={page <= 1 || loading}
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                >
                  <ChevronLeft size={14} /> Previous
                </button>
                <span className="page-indicator">
                  Page {page} of {totalPages}
                </span>
                <button
                  className="button secondary button-sm"
                  disabled={page >= totalPages || loading}
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
