import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { FormEvent } from 'react';
import type { InferenceSelection, JobDetail, NavigationView, Passage, SavedAnalysis, SearchMode, Transcript } from '../api/client';
import { getInferenceProviders, refreshInferenceProviders, searchTranscript } from '../api/client';
import { useAnalyses, useCreateAnalysis, useDeleteAnalysis, useJob } from '../hooks/useJobs';
import { formatTime, passageUtterances, passageWords, selectedWords, transcriptDuration } from '../lib/navigation';
import { analysisDate, analysisOptions, analysisViewLabel, newestAnalyses, selectAnalysis } from '../lib/analyses';
import { isXVideoUrl } from '../lib/video';
import { AnalysisForm } from './AnalysisForm';
import type { AnalysisDraft } from './AnalysisForm';
import { InferenceSettings } from './InferenceSettings';
import { SavedAnalysisDetails } from './SavedAnalysisDetails';
import { NativeVideoPlayer } from './NativeVideoPlayer';
import { YouTubePlayer } from './YouTubePlayer';
import { VideoReference } from './VideoReference';
import { RouteLink } from './RouteLink';
import type { VideoHandle } from './YouTubePlayer';

interface TranscriptViewProps {
  jobId: string;
  analysisId?: string;
  view?: NavigationView;
  onAnalysisChange: (analysisId?: string) => void;
}

function PassageDetail({ transcript, passage, currentTime, onSeek }: {
  transcript: Transcript; passage: Passage | null; currentTime: number; onSeek: (time: number) => void;
}) {
  if (!passage) return (
    <aside className="passage-panel nav-panel">
      <span className="section-eyebrow">Selected passage</span>
      <h2>Select a passage</h2>
      <p>Choose a timed passage in the visualization or search results to read its words here.</p>
    </aside>
  );
  const utterances = passageUtterances(transcript, passage);
  const words = selectedWords(transcript, passage);
  return (
    <aside className="passage-panel nav-panel" aria-label="Selected transcript passage">
      <div className="passage-heading">
        <span className="section-eyebrow">Selected passage</span>
        <button className="nav-link" onClick={() => onSeek(passage.start)} aria-label={`Seek to passage start at ${formatTime(passage.start)}`}>{formatTime(passage.start)}–{formatTime(passage.end)} ↗</button>
      </div>
      <div className="passage-body">
        {utterances.length > 0 && words.length > 0 ? utterances.map((utterance, index) => {
          const utteranceWords = passageWords(words, Math.max(utterance.start, passage.start), Math.min(utterance.end, passage.end));
          if (utteranceWords.length === 0) return null;
          return <div className="passage-utterance" key={`${utterance.start}-${index}`}>
            <div className="passage-speaker"><span>{utterance.speaker || 'Speaker'}</span><span>{formatTime(Math.max(utterance.start, passage.start))}</span></div>
            <p>{utteranceWords.length > 0 ? utteranceWords.map((word, wordIndex) => <span key={`${word.start}-${wordIndex}`}>
              <button className={`transcript-word ${currentTime >= word.start && currentTime < word.end ? 'is-current' : ''}`} title={`Seek to ${formatTime(word.start)}`} onClick={() => onSeek(word.start)}>{word.text}</button>{' '}
            </span>) : passage.text}</p>
          </div>;
        }) : <p>{passage.text}</p>}
      </div>
      <p className="navigation-hint">Click a word to seek. Playback keeps its playing or paused state.</p>
    </aside>
  );
}


function TranscriptWorkspace({ data, analysisId, view, onAnalysisChange }: {
  data: JobDetail & { transcript: Transcript };
  analysisId?: string;
  view?: NavigationView;
  onAnalysisChange: (analysisId?: string) => void;
}) {
  const { job, transcript } = data;
  const analysesQuery = useAnalyses(job.id, data.analyses);
  const analyses = newestAnalyses(analysesQuery.data ?? []);
  const analysis = selectAnalysis(analyses, analysisId, view);
  const selectionScope = analysis?.id ?? analysisId ?? '';
  const [selection, setSelection] = useState<{ analysisId: string; ids: string[]; passage: Passage | null }>({ analysisId: selectionScope, ids: [], passage: null });
  if (selection.analysisId !== selectionScope) setSelection({ analysisId: selectionScope, ids: [], passage: null });
  const selected = selection.analysisId === selectionScope ? selection.passage : null;
  const [selectedTime, setSelectedTime] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [query, setQuery] = useState('');
  const [searchMode, setSearchMode] = useState<SearchMode>('exact');
  const [copyMessage, setCopyMessage] = useState('');
  const [draft, setDraft] = useState<AnalysisDraft | null>(null);
  const [draftInference, setDraftInference] = useState<InferenceSelection | undefined>();
  const [draftCustomModel, setDraftCustomModel] = useState(false);
  const video = useRef<VideoHandle>(null);
  const queryClient = useQueryClient();
  const providers = useQuery({ queryKey: ['inference-providers'], queryFn: getInferenceProviders, staleTime: 15 * 60_000 });
  const [customModel, setCustomModel] = useState(false);
  const [chosenInference, setChosenInference] = useState<InferenceSelection | undefined>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('analysis-inference') || 'null');
      return saved && typeof saved.provider === 'string' && typeof saved.model === 'string' ? saved : undefined;
    } catch { return undefined; }
  });
  const inference = chosenInference ?? (providers.data ? { provider: providers.data.default_provider, model: providers.data.default_model } : undefined);
  const formInference = draftInference ?? inference;
  const inferenceReady = (selection: InferenceSelection | undefined) => !!selection?.model.trim() && !!providers.data?.providers.find((item) => item.id === selection.provider)?.configured;
  const catalogRefresh = useMutation({
    mutationFn: refreshInferenceProviders,
    onMutate: async () => { await queryClient.cancelQueries({ queryKey: ['inference-providers'], exact: true }); },
    onSuccess: (options) => queryClient.setQueryData(['inference-providers'], options),
  });
  const providerError = catalogRefresh.isError ? `Could not refresh models: ${catalogRefresh.error.message}` : providers.isError ? `Could not load models: ${providers.error.message}` : undefined;
  const refreshModels = () => {
    if (inference) setChosenInference(inference);
    if (formInference) setDraftInference(formInference);
    catalogRefresh.mutate();
  };
  const search = useMutation({ mutationFn: ({ query, mode }: { query: string; mode: SearchMode }) => searchTranscript(job.id, query, mode, inference) });
  const changeInference = (value: InferenceSelection) => {
    setChosenInference(value);
    try { localStorage.setItem('analysis-inference', JSON.stringify(value)); } catch { /* Storage may be unavailable. */ }
    search.reset();
  };
  const creation = useCreateAnalysis(job.id);
  const deletion = useDeleteAnalysis(job.id);
  const duration = transcriptDuration(transcript);
  const seek = (time: number) => {
    setSelectedTime(time);
    video.current?.seek(time);
  };
  const selectPassage = (passage: Passage) => {
    setSelection((previous) => ({ ...previous, analysisId: selectionScope, passage }));
    seek(passage.match_start ?? passage.start);
  };
  const beginAnalysis = (source?: SavedAnalysis) => {
    creation.reset();
    setDraft({ name: source?.name ?? '', view: source?.view ?? view ?? 'timeline', prompt: source?.prompt ?? '', sourceId: source?.id });
    setDraftInference(source?.provider && source.model ? { provider: source.provider, model: source.model } : inference);
    setDraftCustomModel(false);
  };
  const submitAnalysis = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft || !formInference || !inferenceReady(formInference)) return;
    creation.mutate({ options: analysisOptions(draft.name, draft.view, draft.prompt, formInference), sourceId: draft.sourceId }, {
      onSuccess: (created) => {
        setDraft(null);
        onAnalysisChange(created.id);
      },
    });
  };
  const selectSavedAnalysis = (id?: string) => {
    setDraft(null);
    creation.reset();
    deletion.reset();
    onAnalysisChange(id);
  };
  const deleteSelectedAnalysis = () => {
    if (!analysis) return;
    deletion.mutate(analysis.id, { onSuccess: () => selectSavedAnalysis() });
  };
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (query.trim()) search.mutate({ query: query.trim(), mode: searchMode });
  };
  const copyTranscript = async () => {
    try {
      await navigator.clipboard.writeText(transcript.transcript_text);
      setCopyMessage('Transcript copied');
    } catch { setCopyMessage('Copy failed. Download the transcript instead.'); }
  };
  const download = (format: 'txt' | 'json') => {
    const content = format === 'json' ? JSON.stringify(transcript, null, 2) : transcript.utterances.map((u) => `[${formatTime(u.start)}] ${u.speaker}: ${u.text}`).join('\n\n');
    const objectUrl = URL.createObjectURL(new Blob([content], { type: format === 'json' ? 'application/json' : 'text/plain' }));
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = `${job.title || job.id}.${format}`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  };

  return <>
    <div className="transcript-toolbar">
      <div className="transcript-statline"><span><strong>{formatTime(duration)}</strong> running time</span><span><strong>{transcript.utterances.length.toLocaleString()}</strong> speaker turns</span></div>
      <div className="transcript-actions">
        <button className="nav-button compact" onClick={copyTranscript}>Copy transcript</button>
        <button className="nav-button compact" onClick={() => download('txt')}>Download TXT</button>
        <button className="nav-button compact" onClick={() => download('json')}>Download JSON</button>
      </div>
    </div>
    {copyMessage && <p className="navigation-hint" role="status">{copyMessage}</p>}

    <div className="watch-layout">
      {isXVideoUrl(job.url)
        ? <NativeVideoPlayer ref={video} jobId={job.id} url={job.url} title={job.title || 'X video'} available={transcript.video_available ?? job.video_available ?? false} selectedTime={selectedTime} onTimeChange={setCurrentTime} />
        : <YouTubePlayer ref={video} url={job.url} title={job.title || 'YouTube video'} selectedTime={selectedTime} onTimeChange={setCurrentTime} />}
      <PassageDetail transcript={transcript} passage={selected} currentTime={currentTime} onSeek={seek} />
    </div>

    <section className="nav-panel search-panel" aria-label="Search this video">
      <form onSubmit={submitSearch} className="transcript-search">
        <div className="search-input-group">
          <label htmlFor="transcript-search" className="section-eyebrow">Search the conversation</label>
          <input id="transcript-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={searchMode === 'exact' ? 'Words or a phrase from this video…' : 'Describe an idea, e.g. why growth slowed…'} />
        </div>
        <div className="search-controls">
          <label className="sr-only" htmlFor="search-mode">Search mode</label>
          <select id="search-mode" value={searchMode} onChange={(event) => setSearchMode(event.target.value as SearchMode)}><option value="exact">Exact words</option><option value="semantic">Meaning</option></select>
          <button className="nav-button primary" type="submit" disabled={search.isPending || !query.trim() || (searchMode === 'semantic' && !inferenceReady(inference))}>{search.isPending ? 'Searching…' : 'Search'}</button>
          {(search.data || search.isError) && <button className="nav-button compact" type="button" onClick={() => search.reset()}>Clear results</button>}
        </div>
      </form>
      {searchMode === 'semantic' && <InferenceSettings options={providers.data} inference={inference} customModel={customModel}
        heading="Meaning search settings" description="Used to find ideas across this video." idPrefix="search"
        loading={providers.isPending && !catalogRefresh.isPending} refreshing={catalogRefresh.isPending} error={providerError}
        onChange={changeInference} onCustomModelChange={setCustomModel} onRefresh={refreshModels} />}
      {search.isPending && <p role="status" className="navigation-hint">Finding passages in this video…</p>}
      {search.isError && <p className="nav-error" role="alert">{search.error.message}</p>}
      {search.data && <div className="search-results">
        <p className="navigation-hint" role="status">{search.data.results.length} passage{search.data.results.length === 1 ? '' : 's'} for “{search.data.query}” · {search.data.mode === 'semantic' ? 'Meaning' : 'Exact words'}</p>
        {search.data.error && <p className="nav-error" role="alert">{search.data.error}</p>}
        {search.data.results.map((passage) => <button key={passage.id} className={`search-result ${selected?.id === passage.id ? 'is-selected' : ''}`} onClick={() => selectPassage(passage)}><span className="tile-time">{formatTime(passage.start)}–{formatTime(passage.end)} ↗</span><span>{passage.text}</span></button>)}
        {search.data.results.length === 0 && !search.data.error && <p className="nav-empty">No passages found. Try different words or switch to Meaning.</p>}
      </div>}
    </section>

    <section className="nav-panel exploration-panel" aria-label="Analyses of this video">
      <div className="exploration-header">
        <div><span className="section-eyebrow">Analyses</span><h2>Explore the conversation</h2></div>
        <div className="analysis-selector-controls">
          {analyses.length > 0 && <label htmlFor="saved-analysis" className="analysis-selector-label"><span className="sr-only">Saved analysis</span><select id="saved-analysis" value={analysis?.id ?? ''} onChange={(event) => selectSavedAnalysis(event.target.value)}>
            {!analysis && <option value="">Choose a saved analysis</option>}
            {analyses.map((item) => <option key={item.id} value={item.id}>{item.name} · {analysisViewLabel(item.view)} · {analysisDate(item.created_at)}{item.status !== 'completed' ? ` · ${item.status}` : ''}</option>)}
          </select></label>}
          <button className="nav-button primary" disabled={creation.isPending} onClick={() => beginAnalysis()}>New analysis</button>
        </div>
      </div>
      {draft && <AnalysisForm draft={draft} onChange={setDraft} onSubmit={submitAnalysis} onCancel={() => { setDraft(null); creation.reset(); }} submitting={creation.isPending} ready={inferenceReady(formInference)} error={creation.isError ? creation.error.message : undefined}
        inferenceSettings={<InferenceSettings options={providers.data} inference={formInference} customModel={draftCustomModel} idPrefix="new-analysis" description="Used for this new analysis version."
          loading={providers.isPending && !catalogRefresh.isPending} refreshing={catalogRefresh.isPending} error={providerError}
          onChange={setDraftInference} onCustomModelChange={setDraftCustomModel} onRefresh={refreshModels} />} />}
      {analysesQuery.isError && <p className="nav-error" role="alert">Could not load saved analyses: {analysesQuery.error.message} <button className="nav-link" onClick={() => analysesQuery.refetch()}>Try again</button></p>}
      {deletion.isError && <p className="nav-error" role="alert">Could not delete analysis: {deletion.error.message}</p>}
      {analysis ? <SavedAnalysisDetails analysis={analysis} providers={providers.data} duration={duration} currentTime={currentTime} selected={selected} onSelect={selectPassage}
        timelineSelection={selection.analysisId === analysis.id ? selection.ids : []} onTimelineSelectionChange={(ids) => setSelection((previous) => ({ ...previous, analysisId: analysis.id, ids }))}
        onRegenerate={() => beginAnalysis(analysis)} onDelete={deleteSelectedAnalysis} deleting={deletion.isPending} />
        : analysesQuery.isPending || analysesQuery.isFetching ? <p className="nav-loading" role="status">Loading saved analyses…</p>
          : analysisId !== undefined ? <p className="nav-error" role="alert">Analysis “{analysisId}” was not found for this video. <button className="nav-link" onClick={() => selectSavedAnalysis()}>Show newest analysis</button></p>
            : !analysesQuery.isError && !draft ? <div className="creation-state"><h3>Give the conversation a perspective</h3><p>Create an analysis with a summary and either a Timeline or Topics visualization. Add a prompt to refine its focus.</p></div> : null}
    </section>
  </>;
}

export function TranscriptView({ jobId, analysisId, view, onAnalysisChange }: TranscriptViewProps) {
  const { data, isLoading, error } = useJob(jobId);
  return <main className="transcript-page animate-fade-in">
    <RouteLink className="transcript-back" href="/">← The archive</RouteLink>
    {isLoading && <div className="transcript-loading" role="status"><div className="skeleton h-8 w-2/3 mb-6" /><div className="skeleton h-72 w-full" /><span className="sr-only">Loading transcript</span></div>}
    {error && <p className="nav-error" role="alert">Error loading transcript: {error.message}</p>}
    {data && <>
      <header className="transcript-header">
        <span className="section-eyebrow">{isXVideoUrl(data.job.url) ? 'X' : 'YouTube'} · Transcript &amp; analyses</span>
        <h1>{data.job.title || 'Untitled video'}</h1>
        <div className="transcript-reference"><a href={data.job.url} target="_blank" rel="noopener noreferrer">View original on {isXVideoUrl(data.job.url) ? 'X' : 'YouTube'} ↗</a><VideoReference id={data.job.id} /></div>
      </header>
      {data.transcript ? <TranscriptWorkspace key={jobId} data={{ ...data, transcript: data.transcript }} analysisId={analysisId} view={view} onAnalysisChange={onAnalysisChange} /> : <p className="nav-empty">No transcript available.</p>}
    </>}
  </main>;
}
