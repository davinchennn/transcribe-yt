import type { FormEvent, ReactNode } from 'react';
import type { NavigationView } from '../api/client';

export interface AnalysisDraft {
  name: string;
  view: NavigationView;
  prompt: string;
  sourceId?: string;
}

export function AnalysisForm({ draft, onChange, onSubmit, onCancel, inferenceSettings, submitting, ready, error }: {
  draft: AnalysisDraft;
  onChange: (draft: AnalysisDraft) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  inferenceSettings: ReactNode;
  submitting: boolean;
  ready: boolean;
  error?: string;
}) {
  return <form className="analysis-form" aria-label={draft.sourceId ? 'Create another analysis version' : 'New analysis'} onSubmit={onSubmit}>
    <h3>{draft.sourceId ? 'Create another version' : 'New analysis'}</h3>
    <div className="analysis-form-fields">
      <label htmlFor="new-analysis-name">Name <span className="navigation-hint">Optional</span>
        <input id="new-analysis-name" value={draft.name} maxLength={200} placeholder={draft.view === 'timeline' ? 'Timeline' : 'Topics'} onChange={(event) => onChange({ ...draft, name: event.target.value })} />
      </label>
      <label htmlFor="new-analysis-view">Visualization
        <select id="new-analysis-view" value={draft.view} onChange={(event) => onChange({ ...draft, view: event.target.value as NavigationView })}>
          <option value="timeline">Timeline</option><option value="topics">Topics</option>
        </select>
      </label>
      <label className="analysis-prompt-field" htmlFor="new-analysis-prompt">Focus prompt <span className="navigation-hint">Optional</span>
        <textarea id="new-analysis-prompt" rows={3} value={draft.prompt} maxLength={10000} placeholder="Emphasize engineering tradeoffs and explain the decisions discussed…" onChange={(event) => onChange({ ...draft, prompt: event.target.value })} />
      </label>
    </div>
    <p className="navigation-hint">{draft.view === 'timeline' ? 'The timeline always covers the whole video. Your prompt refines its chapters, subtopics, and summary.' : 'Your prompt refines the subjects, their occurrences, and the summary.'}</p>
    {inferenceSettings}
    {error && <p className="nav-error" role="alert">{error}</p>}
    <div className="analysis-form-actions">
      <button className="nav-button primary" type="submit" disabled={submitting || !ready}>{submitting ? 'Starting…' : draft.sourceId ? 'Create version' : 'Create analysis'}</button>
      <button className="nav-button compact" type="button" disabled={submitting} onClick={onCancel}>Cancel</button>
      {draft.sourceId && <span className="navigation-hint">Your saved versions stay available.</span>}
    </div>
  </form>;
}
