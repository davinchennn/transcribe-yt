import type { InferenceOptions, Passage, SavedAnalysis } from '../api/client';
import { analysisDate, analysisViewLabel } from '../lib/analyses';
import { inferenceLabel } from '../lib/inference';
import { NavigationCanvas } from './NavigationCanvas';

export function SavedAnalysisDetails({ analysis, providers, duration, currentTime, selected, onSelect, timelineSelection, onTimelineSelectionChange, onRegenerate, onDelete, deleting }: {
  analysis: SavedAnalysis;
  providers: InferenceOptions | undefined;
  duration: number;
  currentTime: number;
  selected: Passage | null;
  onSelect: (passage: Passage) => void;
  timelineSelection: string[];
  onTimelineSelectionChange: (ids: string[]) => void;
  onRegenerate: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  const processing = analysis.status === 'pending' || analysis.status === 'processing';
  return <div className="saved-analysis">
    <div className="saved-analysis-heading"><h3>{analysis.name}</h3><span className="analysis-view-label">{analysisViewLabel(analysis.view)}</span></div>
    <div className="analysis-meta">
      <span className="navigation-hint">Version saved {analysisDate(analysis.created_at)}</span>
      <span className="navigation-hint" title={analysis.model || undefined}>{inferenceLabel(providers, analysis.provider, analysis.model)}</span>
      <button className="nav-button compact" onClick={onRegenerate}>{analysis.status === 'failed' ? 'Retry as new version' : 'Create another version'}</button>
      <button className="nav-button compact" disabled={deleting} onClick={onDelete}>{deleting ? 'Deleting…' : 'Delete analysis'}</button>
    </div>
    {analysis.prompt && <details className="saved-analysis-prompt"><summary>Focus prompt</summary><p>{analysis.prompt}</p></details>}
    {processing ? <div className="creation-state" role="status" aria-live="polite"><span className="creation-spinner" /><h3>Creating analysis…</h3><p>The summary and {analysis.view === 'topics' ? 'topics' : 'timeline'} will appear here when ready.</p></div>
      : analysis.status === 'failed' ? <p className="nav-error" role="alert">{analysis.error || 'Analysis failed. Create another version to retry.'}</p>
        : analysis.status === 'completed' ? <>
          <div className="saved-analysis-summary" aria-label="Analysis summary">
            {analysis.summary && <p>{analysis.summary}</p>}
            {analysis.key_points.length > 0 && <ul>{analysis.key_points.map((point, index) => <li key={index}>{point}</li>)}</ul>}
          </div>
          {analysis.view && <NavigationCanvas key={analysis.id} analysis={{ ...analysis, view: analysis.view, summary: null }} duration={duration} currentTime={currentTime} selected={selected} onSelect={onSelect} timelineSelection={timelineSelection} onTimelineSelectionChange={onTimelineSelectionChange} />}
        </> : <p className="nav-error" role="alert">Unknown analysis status: {analysis.status}</p>}
  </div>;
}
