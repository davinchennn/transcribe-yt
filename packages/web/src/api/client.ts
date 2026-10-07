/**
 * API client for transcripts backend.
 */

export interface Job {
  id: string;
  url: string;
  stage: string;
  title: string | null;
  error: string | null;
  provider: string | null;
  created_at: string;
  updated_at: string;
  video_available: boolean;
}

export interface Word {
  text: string;
  start: number;
  end: number;
  confidence: number | null;
  speaker: string | null;
}

export interface Utterance {
  speaker: string;
  text: string;
  start: number;
  end: number;
}

export interface Transcript {
  video_url: string;
  video_available: boolean;
  title: string;
  duration: number | null;
  transcript_text: string;
  words: Word[];
  utterances: Utterance[];
}

export interface Analysis {
  job_id: string;
  status: string;
  summary: string | null;
  key_points: string[];
  model: string | null;
  provider?: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobDetail {
  job: Job;
  transcript: Transcript | null;
  analysis: Analysis | null;
  navigation?: Partial<Record<NavigationView, NavigationAnalysis | null>>;
}

export type NavigationView = 'timeline' | 'topics';
export type SearchMode = 'exact' | 'semantic';

export interface Passage {
  id: string;
  start: number;
  end: number;
  text: string;
  utterance_start: number;
  utterance_end: number;
  word_start?: number | null;
  word_end?: number | null;
  match_start?: number | null;
  match_end?: number | null;
}

export interface NavigationNode {
  id: string;
  title: string;
  summary: string | null;
  start: number;
  end: number;
  children: NavigationNode[];
  occurrences: Passage[];
}

export interface NavigationAnalysis {
  job_id: string;
  view: NavigationView;
  status: string;
  summary: string | null;
  nodes: NavigationNode[];
  model: string | null;
  provider?: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  results: Passage[];
  error: string | null;
}

export interface JobListResponse {
  jobs: Job[];
  total: number;
}

export interface CreateJobOptions {
  url: string;
  keep_video?: boolean;
  keep_audio?: boolean;
}

export interface InferenceSelection {
  provider: string;
  model: string;
}

export interface InferenceModel {
  id: string;
  name: string;
  context_length: number | null;
}

export interface InferenceProvider {
  id: string;
  label: string;
  configured: boolean;
  default_model: string;
  models: InferenceModel[];
  catalog_status: 'ready' | 'stale' | 'error' | 'unconfigured';
  catalog_updated_at: string | null;
  catalog_error: string | null;
}

export interface InferenceOptions {
  default_provider: string;
  default_model: string;
  providers: InferenceProvider[];
}

export async function getInferenceProviders(): Promise<InferenceOptions> {
  return fetchJson(`${API_BASE}/inference/providers`);
}

export async function refreshInferenceProviders(): Promise<InferenceOptions> {
  return fetchJson(`${API_BASE}/inference/providers/refresh`, { method: 'POST' });
}

const API_BASE = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.detail || error.error || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function listJobs(stage?: string): Promise<JobListResponse> {
  const params = stage ? `?stage=${stage}` : '';
  return fetchJson(`${API_BASE}/jobs${params}`);
}

export async function createJob(options: CreateJobOptions): Promise<Job> {
  return fetchJson(`${API_BASE}/jobs`, {
    method: 'POST',
    body: JSON.stringify({
      url: options.url,
      keep_video: options.keep_video ?? true,
      keep_audio: options.keep_audio ?? true,
    }),
  });
}

export async function getJob(id: string): Promise<JobDetail> {
  return fetchJson(`${API_BASE}/jobs/${id}`);
}

export function getVideoUrl(id: string): string {
  return `${API_BASE}/jobs/${encodeURIComponent(id)}/video`;
}

export async function retryJob(id: string): Promise<Job> {
  return fetchJson(`${API_BASE}/jobs/${id}/retry`, {
    method: 'POST',
  });
}

export async function deleteJob(id: string): Promise<void> {
  await fetchJson(`${API_BASE}/jobs/${id}`, {
    method: 'DELETE',
  });
}

export async function clearJobs(stage?: string): Promise<{ cleared: number }> {
  const params = stage ? `?stage=${stage}` : '';
  return fetchJson(`${API_BASE}/jobs${params}`, {
    method: 'DELETE',
  });
}

export async function analyzeJob(id: string, selection?: InferenceSelection): Promise<Analysis> {
  return fetchJson(`${API_BASE}/jobs/${id}/analyze`, {
    method: 'POST',
    body: JSON.stringify(selection),
  });
}

export async function getNavigation(id: string, view: NavigationView): Promise<NavigationAnalysis | null> {
  return fetchJson(`${API_BASE}/jobs/${id}/navigation/${view}`);
}

export async function createNavigation(id: string, view: NavigationView, selection?: InferenceSelection): Promise<NavigationAnalysis> {
  return fetchJson(`${API_BASE}/jobs/${id}/navigation/${view}`, { method: 'POST', body: JSON.stringify(selection) });
}

export async function updateNavigationSummaries(id: string, view: NavigationView, selection?: InferenceSelection): Promise<NavigationAnalysis> {
  return fetchJson(`${API_BASE}/jobs/${id}/navigation/${view}/summaries`, { method: 'POST', body: JSON.stringify(selection) });
}

export async function searchTranscript(id: string, query: string, mode: SearchMode, selection?: InferenceSelection): Promise<SearchResponse> {
  return fetchJson(`${API_BASE}/jobs/${id}/search`, {
    method: 'POST',
    body: JSON.stringify({ query, mode, ...selection }),
  });
}
