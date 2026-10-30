import type { Filters, Job } from './types';

// For you ranks HigherEdJobs only and hides nothing by default; Skipped stays out as on other tabs.
export const forYouDefaults: Filters = { query: '', sponsorship: '', hide: '', application_status: 'open', days: 'all', sort: 'fit', min_fit: '' };

// Rows below this fit are dimmed, never removed.
export const lowFit = 40;

export type Tone = 'match' | 'gap' | 'flag';
export type Tag = { label: string; tone: Tone };

// Matched skills first, then gaps, then seniority flags: the order a reader weighs them.
export const whyTags = (job: Job): Tag[] => [
  ...(job.fit_details.matched ?? []).map(label => ({ label, tone: 'match' as const })),
  ...[...(job.fit_details.declined ?? []), ...(job.fit_details.missing ?? [])].map(label => ({ label, tone: 'gap' as const })),
  ...job.seniority_flags.map(flag => ({ label: flag.label, tone: 'flag' as const })),
];

export const postedLabel = (days: number | null) => days === null ? 'Posting date unknown'
  : days <= 0 ? 'Posted today' : days === 1 ? 'Posted yesterday' : `Posted ${days} days ago`;
