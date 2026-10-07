import { useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import type { FormEvent } from 'react';
import type { JobDetail, NavigationNode, NavigationView, Passage, SearchMode, Transcript } from '../api/client';
import { searchTranscript } from '../api/client';
import { useAnalyzeJob, useCreateNavigation, useJob, useNavigation, useUpdateNavigationSummaries } from '../hooks/useJobs';
import { formatTime, passageUtterances, passageWords, selectedWords, transcriptDuration } from '../lib/navigation';
import { isXVideoUrl } from '../lib/video';
import { NavigationCanvas } from './NavigationCanvas';
import { NativeVideoPlayer } from './NativeVideoPlayer';
import { YouTubePlayer } from './YouTubePlayer';
import { VideoReference } from './VideoReference';
import { RouteLink } from './RouteLink';
import type { VideoHandle } from './YouTubePlayer';

interface TranscriptViewProps {
  jobId: string;
  view: NavigationView;
  onViewChange: (view: NavigationView) => void;
}

function isProcessing(status?: string): boolean {
  return status === 'pending' || status === 'processing';
}

function needsSubtopicSummaries(nodes: NavigationNode[], depth = 0): boolean {
  return nodes.some((node) => {
    const words = node.summary?.trim().split(/\s+/).filter(Boolean).length ?? 0;
    return (depth > 0 && (words === 0 || words > 20))
      || needsSubtopicSummaries(node.children, depth + 1);
  });
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

function TranscriptWorkspace({ data, view, onViewChange }: {
  data: JobDetail & { transcript: Transcript };
  view: NavigationView;
  onViewChange: (view: NavigationView) => void;
}) {
  const { job, transcript } = data;
  const [timelineSelection, setTimelineSelection] = useState<{ analysisKey: string; ids: string[] }>({ analysisKey: '', ids: [] });
  const [selected, setSelected] = useState<Passage | null>(null);
  const [selectedTime, setSelectedTime] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [query, setQuery] = useState('');
  const [searchMode, setSearchMode] = useState<SearchMode>('exact');
  const [copyMessage, setCopyMessage] = useState('');
  const video = useRef<VideoHandle>(null);
  const activeQuery = useNavigation(job.id, view);
  const creation = useCreateNavigation(job.id);
  const summaryUpdate = useUpdateNavigationSummaries(job.id);
  const summaryMutation = useAnalyzeJob();
  const search = useMutation({ mutationFn: ({ query, mode }: { query: string; mode: SearchMode }) => searchTranscript(job.id, query, mode) });
  const analysis = activeQuery.isError || (activeQuery.isFetching && !isProcessing(activeQuery.data?.status))
    ? undefined : activeQuery.data;
  const creating = (creation.isPending && creation.variables === view) || isProcessing(analysis?.status);
  const checking = activeQuery.isFetching && !creating;
  const duration = transcriptDuration(transcript);
  const viewLabel = view === 'timeline' ? 'Timeline' : 'Topics';
  const timelineAnalysisKey = `${job.id}:${(view === 'timeline' ? analysis : data.navigation?.timeline)?.updated_at ?? ''}`;

  const seek = (time: number) => {
    setSelectedTime(time);
    video.current?.seek(time);
  };
  const selectPassage = (passage: Passage) => {
    setSelected(passage);
    seek(passage.match_start ?? passage.start);
  };
  const createView = () => {
    creation.reset();
    creation.mutate(view);
  };
  const updateSummaries = () => {
    summaryUpdate.reset();
    summaryUpdate.mutate(view, {
      onSuccess: (updated) => {
        if (updated.view === 'timeline') {
          setTimelineSelection((previous) => ({ ...previous, analysisKey: `${job.id}:${updated.updated_at}` }));
        }
      },
    });
  };
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (query.trim()) search.mutate({ query: query.trim(), mode: searchMode });
  };
  const copyTranscript = async () => {
    try {
      await navigator.clipboard.writeText(transcript.transcript_text);
      setCopyMessage('Transcript copied');
    } catch {
      setCopyMessage('Copy failed. Download the transcript instead.');
    }
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

  return (
    <>
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
            <select id="search-mode" value={searchMode} onChange={(event) => setSearchMode(event.target.value as SearchMode)}>
              <option value="exact">Exact words</option><option value="semantic">Meaning</option>
            </select>
            <button className="nav-button primary" type="submit" disabled={search.isPending || !query.trim()}>{search.isPending ? 'Searching…' : 'Search'}</button>
            {(search.data || search.isError) && <button className="nav-button compact" type="button" onClick={() => search.reset()}>Clear results</button>}
          </div>
        </form>
        {search.isPending && <p role="status" className="navigation-hint">Finding passages in this video…</p>}
        {search.isError && <p className="nav-error" role="alert">{search.error.message}</p>}
        {search.data && <div className="search-results">
          <p className="navigation-hint" role="status">{search.data.results.length} passage{search.data.results.length === 1 ? '' : 's'} for “{search.data.query}” · {search.data.mode === 'semantic' ? 'Meaning' : 'Exact words'}</p>
          {search.data.error && <p className="nav-error" role="alert">{search.data.error}</p>}
          {search.data.results.map((passage) => <button key={passage.id} className={`search-result ${selected?.id === passage.id ? 'is-selected' : ''}`} onClick={() => selectPassage(passage)}>
            <span className="tile-time">{formatTime(passage.start)}–{formatTime(passage.end)} ↗</span>
            <span>{passage.text}</span>
          </button>)}
          {search.data.results.length === 0 && !search.data.error && <p className="nav-empty">No passages found. Try different words or switch to Meaning.</p>}
        </div>}
      </section>

      <section className="nav-panel exploration-panel" aria-label="Explore this video">
        <div className="exploration-header">
          <div><span className="section-eyebrow">Navigation</span><h2>Explore the conversation</h2></div>
          <div className="view-switch" role="group" aria-label="Navigation view">
            {(['timeline', 'topics'] as const).map((item) => {
              const saved = item === view ? analysis : data.navigation?.[item];
              return <button key={item} className={item === view ? 'is-active' : ''} aria-pressed={item === view} onClick={() => {
                if (item === view) void activeQuery.refetch();
                else onViewChange(item);
              }}>
                {item === 'timeline' ? 'Timeline' : 'Topics'}<span>{item === view && checking ? 'Checking…' : saved?.status === 'completed' ? 'Ready' : isProcessing(saved?.status) ? 'Creating…' : 'Not created'}</span>
              </button>;
            })}
          </div>
        </div>
        {checking && <p className="nav-loading" role="status">Checking saved {viewLabel.toLowerCase()}…</p>}
        {activeQuery.isError && <p className="nav-error" role="alert">Could not load this view: {activeQuery.error.message} <button className="nav-link" onClick={() => activeQuery.refetch()}>Try again</button></p>}
        {analysis?.status === 'completed' && (needsSubtopicSummaries(analysis.nodes) || (summaryUpdate.isPending && summaryUpdate.variables === view)) && <div className="subtopic-summary-update">
          <button className="nav-button compact" disabled={summaryUpdate.isPending} onClick={updateSummaries}>{summaryUpdate.isPending && summaryUpdate.variables === view ? 'Updating summaries…' : 'Update summaries'}</button>
          <span className="navigation-hint">20 words or fewer per subtopic, using terms from this transcript.</span>
        </div>}
        {summaryUpdate.isError && summaryUpdate.variables === view && <p className="nav-error" role="alert">Could not update subtopic summaries: {summaryUpdate.error.message}</p>}
        {creating ? <div className="creation-state" role="status" aria-live="polite"><span className="creation-spinner" /><h3>Creating {viewLabel.toLowerCase()}…</h3><p>Analyzing this transcript. The view will appear here when it is ready.</p></div> : analysis?.status === 'completed' ? (
          <NavigationCanvas analysis={analysis} duration={duration} currentTime={currentTime} selected={selected} onSelect={selectPassage}
            timelineSelection={timelineSelection.analysisKey === timelineAnalysisKey ? timelineSelection.ids : []}
            onTimelineSelectionChange={(ids) => setTimelineSelection({ analysisKey: timelineAnalysisKey, ids })} />
        ) : !checking && !activeQuery.isError ? <div className="creation-state">
          <span className="view-icon" aria-hidden="true">{view === 'timeline' ? '▥' : '≋'}</span>
          <h3>{view === 'timeline' ? 'See how the discussion unfolds' : 'Find subjects wherever they recur'}</h3>
          <p>{view === 'timeline' ? 'Create chronological chapters and nested subtopics. Keep the chapter overview visible while selecting subtopics to explore.' : 'Create a hierarchy of subjects and subtopics. See every level together, with each occurrence mapped across the video.'}</p>
          {(analysis?.status === 'failed' || (creation.isError && creation.variables === view)) && <p className="nav-error" role="alert">{analysis?.error || creation.error?.message || 'Analysis failed. Try again.'}</p>}
          <button className="nav-button primary" onClick={createView} disabled={creation.isPending}>{analysis?.status === 'failed' ? `Retry ${viewLabel}` : `Create ${viewLabel}`}</button>
          <span className="navigation-hint">Created only when you ask. Saved for this video.</span>
        </div> : null}
      </section>

      <details className="nav-panel summary-panel">
        <summary>The conversation at a glance</summary>
        {data.analysis?.status === 'completed' ? <>
          <p>{data.analysis.summary}</p>
          {data.analysis.key_points.length > 0 && <ul>{data.analysis.key_points.map((point, index) => <li key={index}>{point}</li>)}</ul>}
        </> : isProcessing(data.analysis?.status) ? <p role="status">Analyzing summary…</p> : <>
          {data.analysis?.error && <p className="nav-error" role="alert">{data.analysis.error}</p>}
          {summaryMutation.isError && <p className="nav-error" role="alert">{summaryMutation.error.message}</p>}
          <button className="nav-button compact" disabled={summaryMutation.isPending} onClick={() => summaryMutation.mutate(job.id)}>{summaryMutation.isPending ? 'Starting…' : data.analysis?.status === 'failed' ? 'Retry summary' : 'Create summary'}</button>
        </>}
      </details>
    </>
  );
}

export function TranscriptView({ jobId, view, onViewChange }: TranscriptViewProps) {
  const { data, isLoading, error } = useJob(jobId);
  return (
    <main className="transcript-page animate-fade-in">
      <RouteLink className="transcript-back" href="/">← The archive</RouteLink>
      {isLoading && <div className="transcript-loading" role="status"><div className="skeleton h-8 w-2/3 mb-6" /><div className="skeleton h-72 w-full" /><span className="sr-only">Loading transcript</span></div>}
      {error && <p className="nav-error" role="alert">Error loading transcript: {error.message}</p>}
      {data && <>
        <header className="transcript-header">
          <span className="section-eyebrow">{isXVideoUrl(data.job.url) ? 'X' : 'YouTube'} · Transcript &amp; visual guide</span>
          <h1>{data.job.title || 'Untitled video'}</h1>
          <div className="transcript-reference">
            <a href={data.job.url} target="_blank" rel="noopener noreferrer">View original on {isXVideoUrl(data.job.url) ? 'X' : 'YouTube'} ↗</a>
            <VideoReference id={data.job.id} />
          </div>
        </header>
        {data.transcript ? <TranscriptWorkspace key={jobId} data={{ ...data, transcript: data.transcript }} view={view} onViewChange={onViewChange} /> : <p className="nav-empty">No transcript available.</p>}
      </>}
    </main>
  );
}
