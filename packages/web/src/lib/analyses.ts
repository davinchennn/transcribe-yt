import type { CreateAnalysisOptions, InferenceSelection, NavigationView, SavedAnalysis } from '../api/client';

export function newestAnalyses(analyses: SavedAnalysis[]): SavedAnalysis[] {
  return [...analyses].sort((left, right) => analysisTimestamp(right.created_at) - analysisTimestamp(left.created_at));
}

export function selectAnalysis(analyses: SavedAnalysis[], analysisId?: string, legacyView?: NavigationView): SavedAnalysis | undefined {
  const sorted = newestAnalyses(analyses);
  if (analysisId !== undefined) return sorted.find((analysis) => analysis.id === analysisId);
  return legacyView ? sorted.find((analysis) => analysis.view === legacyView) ?? sorted[0] : sorted[0];
}

export function analysisOptions(name: string, view: NavigationView, prompt: string, inference: InferenceSelection): CreateAnalysisOptions {
  return { name: name.trim() || (view === 'timeline' ? 'Timeline' : 'Topics'), view, prompt: prompt.trim(), ...inference };
}

export function analysisDate(value: string): string {
  return new Date(analysisTimestamp(value)).toLocaleString();
}

function analysisTimestamp(value: string): number {
  return Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`);
}

export function analysisViewLabel(view: NavigationView | null): string {
  return view === 'timeline' ? 'Timeline' : view === 'topics' ? 'Topics' : 'General summary';
}
