import React from 'react';
import { useJob, useAnalyzeJob } from '../hooks/useJobs';

interface TranscriptViewProps {
  jobId: string;
  onClose: () => void;
}

const speakerColors = [
  '#818cf8', // indigo
  '#34d399', // emerald
  '#fb923c', // orange
  '#f472b6', // pink
  '#38bdf8', // sky
  '#a78bfa', // violet
  '#fbbf24', // amber
  '#2dd4bf', // teal
];

function getSpeakerColor(speaker: string, speakerMap: Map<string, string>): string {
  if (!speakerMap.has(speaker)) {
    speakerMap.set(speaker, speakerColors[speakerMap.size % speakerColors.length]);
  }
  return speakerMap.get(speaker)!;
}

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function isAnalysisInProgress(status?: string): boolean {
  return status === 'pending' || status === 'processing';
}

export function TranscriptView({ jobId, onClose }: TranscriptViewProps) {
  const [polling, setPolling] = React.useState(false);
  const { data, isLoading, error } = useJob(jobId, polling ? 2000 : false);
  const analyzeMutation = useAnalyzeJob();

  // Start/stop polling based on analysis status
  React.useEffect(() => {
    setPolling(isAnalysisInProgress(data?.analysis?.status));
  }, [data?.analysis?.status]);

  const handleCopy = () => {
    if (data?.transcript) {
      navigator.clipboard.writeText(data.transcript.transcript_text);
    }
  };

  const handleDownload = (format: 'txt' | 'json') => {
    if (!data?.transcript) return;

    let content: string;
    let filename: string;
    let type: string;

    if (format === 'json') {
      content = JSON.stringify(data.transcript, null, 2);
      filename = `${data.job.title || data.job.id}.json`;
      type = 'application/json';
    } else {
      content = data.transcript.utterances
        .map((u) => `[${u.speaker}]: ${u.text}`)
        .join('\n\n');
      filename = `${data.job.title || data.job.id}.txt`;
      type = 'text/plain';
    }

    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const speakerMap = new Map<string, string>();

  return (
    <div className="max-w-4xl mx-auto px-6 py-10 animate-fade-in">
      {/* Top bar */}
      <div className="flex items-center justify-between mb-8">
        <button
          onClick={onClose}
          className="flex items-center gap-2 text-sm font-medium transition-colors cursor-pointer"
          style={{ color: 'var(--text-secondary)' }}
          onMouseEnter={(e) => e.currentTarget.style.color = 'var(--text-primary)'}
          onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Back
        </button>

        {data?.transcript && (
          <div className="flex gap-2">
            {(!data.analysis || data.analysis.status === 'failed') && (
              <button
                onClick={() => { analyzeMutation.mutate(jobId); setPolling(true); }}
                disabled={analyzeMutation.isPending}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors cursor-pointer"
                style={{
                  color: '#818cf8',
                  borderColor: '#818cf8',
                  backgroundColor: 'transparent',
                  opacity: analyzeMutation.isPending ? 0.5 : 1,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'rgba(129,140,248,0.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                {analyzeMutation.isPending ? 'Starting...' : data.analysis?.status === 'failed' ? 'Retry Analysis' : 'Analyze'}
              </button>
            )}
            <button
              onClick={handleCopy}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors cursor-pointer"
              style={{
                color: 'var(--text-secondary)',
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-surface)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-bright)';
                e.currentTarget.style.backgroundColor = 'var(--bg-elevated)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border)';
                e.currentTarget.style.backgroundColor = 'var(--bg-surface)';
              }}
            >
              Copy
            </button>
            <button
              onClick={() => handleDownload('txt')}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors cursor-pointer"
              style={{
                color: 'var(--text-secondary)',
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-surface)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-bright)';
                e.currentTarget.style.backgroundColor = 'var(--bg-elevated)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border)';
                e.currentTarget.style.backgroundColor = 'var(--bg-surface)';
              }}
            >
              Download TXT
            </button>
            <button
              onClick={() => handleDownload('json')}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors cursor-pointer"
              style={{
                color: 'var(--text-secondary)',
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-surface)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-bright)';
                e.currentTarget.style.backgroundColor = 'var(--bg-elevated)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border)';
                e.currentTarget.style.backgroundColor = 'var(--bg-surface)';
              }}
            >
              Download JSON
            </button>
          </div>
        )}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="py-20">
          <div className="skeleton h-8 w-2/3 mb-3 mx-auto" />
          <div className="skeleton h-4 w-1/3 mb-12 mx-auto" />
          <div className="space-y-6">
            {[...Array(5)].map((_, i) => (
              <div key={i}>
                <div className="skeleton h-3 w-24 mb-2" />
                <div className="skeleton h-4 w-full mb-1" />
                <div className="skeleton h-4 w-3/4" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="text-center py-20" style={{ color: 'var(--status-failed)' }}>
          Error loading transcript: {error.message}
        </div>
      )}

      {/* Content */}
      {data && (
        <>
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>
              {data.job.title || 'Untitled'}
            </h1>
            <a
              href={data.job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-mono transition-colors"
              style={{ color: 'var(--text-muted)' }}
              onMouseEnter={(e) => e.currentTarget.style.color = 'var(--accent)'}
              onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
            >
              {data.job.url}
            </a>
          </div>

          {/* Analysis section */}
          {data.analysis && (
            <div
              className="rounded-xl border p-6 mb-8"
              style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border)' }}
            >
              {/* Pending / Processing */}
              {isAnalysisInProgress(data.analysis.status) && (
                <div className="flex items-center gap-3">
                  <span className="relative flex h-2.5 w-2.5">
                    <span
                      className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                      style={{ backgroundColor: '#818cf8' }}
                    />
                    <span
                      className="relative inline-flex rounded-full h-2.5 w-2.5"
                      style={{ backgroundColor: '#818cf8' }}
                    />
                  </span>
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                    Analyzing transcript...
                  </span>
                </div>
              )}

              {/* Failed */}
              {data.analysis.status === 'failed' && (
                <div className="text-sm" style={{ color: 'var(--status-failed)' }}>
                  Analysis failed: {data.analysis.error}
                </div>
              )}

              {/* Completed */}
              {data.analysis.status === 'completed' && (
                <div>
                  <h3
                    className="text-sm font-semibold uppercase tracking-wider mb-4"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    Analysis
                  </h3>
                  {data.analysis.summary && (
                    <p className="text-sm leading-relaxed mb-4" style={{ color: 'var(--text-secondary)' }}>
                      {data.analysis.summary}
                    </p>
                  )}
                  {data.analysis.key_points.length > 0 && (
                    <ul className="space-y-1.5 mb-4">
                      {data.analysis.key_points.map((point, i) => (
                        <li key={i} className="flex gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                          <span style={{ color: 'var(--text-muted)' }}>&#8226;</span>
                          {point}
                        </li>
                      ))}
                    </ul>
                  )}
                  {data.analysis.model && (
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      Model: {data.analysis.model}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Video player slot (future) */}
          {/* <div className="rounded-xl border mb-8" style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border)' }}>
            <div className="aspect-video flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
              Video player placeholder
            </div>
          </div> */}

          {/* Visualizations slot (future) */}
          {/* <div className="rounded-xl border p-6 mb-8" style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border)' }}>
            <div className="h-24 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
              Speaker timeline / visualizations placeholder
            </div>
          </div> */}

          {/* Transcript */}
          {data.transcript ? (
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider mb-6" style={{ color: 'var(--text-muted)' }}>
                Transcript
              </h2>
              <div
                className="border-t"
                style={{ borderColor: 'var(--border)' }}
              >
                {data.transcript.utterances.map((utterance, i) => {
                  const color = getSpeakerColor(utterance.speaker, speakerMap);
                  return (
                    <div
                      key={i}
                      className="py-4 border-b"
                      style={{ borderColor: 'var(--border)' }}
                    >
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-xs font-medium" style={{ color }}>
                          {utterance.speaker}
                        </span>
                        <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                          {formatTimestamp(utterance.start)}
                        </span>
                      </div>
                      <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                        {utterance.text}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="text-center py-20" style={{ color: 'var(--text-muted)' }}>
              No transcript available
            </div>
          )}
        </>
      )}
    </div>
  );
}
