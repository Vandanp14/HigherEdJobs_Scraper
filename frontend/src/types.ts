// Fit breakdown stored by backend/app/fit.py score_job. Empty for jobs scored without a resume.
export type FitDetails = {
  score?: number;
  matched?: string[];
  missing?: string[];
  declined?: string[];
  required_total?: number;
  required_matched?: number;
  parts?: { skills: number; role: number; sponsorship: number; seniority: number };
  reasons?: string[];
};

export type Job = {
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
  signals: string;
  evidence: string | null;
  evidence_context: string | null;
  normalized_description: string | null;
  application_status: string;
  apply_url: string | null;
  description_status: string;
  seniority_flags: { label: string; evidence: string }[];
  fit_score: number | null;
  fit_details: FitDetails;
  rank_value: number;
  age_days: number | null;
};

export type Filters = Record<string, string>;

// Whether the For you ranking has a readable resume behind it, and where it is read from.
export type ResumeState = { loaded: boolean; path: string | null };

// Mirrors LABELS in backend/app/seniority.py.
export const seniorityLabels = ['Director', 'Postdoc / PhD', 'Leadership', 'Senior / Lead', 'Level III+', '5+ years', "Master's required"];
export const sponsorshipLabels = [['Not Worth It', 'Not worth it'], ['Likely No Sponsorship', 'Likely no sponsorship'], ['Unsure - Review', 'Review needed'], ['No Mention Found', 'No mention found'], ['Sponsorship Possible', 'Sponsorship possible']];

export const signalClass = (signal: string) => ({
  'Not Worth It': 'signal-stop',
  'Likely No Sponsorship': 'signal-caution',
  'Unsure - Review': 'signal-review',
  'Sponsorship Possible': 'signal-positive',
  'No Mention Found': 'signal-empty',
}[signal] || 'signal-empty');

export const toggleItem = (list: string[], item: string) => (list.includes(item)
  ? list.filter(value => value !== item)
  : [...list, item]).join(',');
