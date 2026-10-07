import type { Job } from '../api/client';
import { useRetryJob, useDeleteJob } from '../hooks/useJobs';
import { VideoReference } from './VideoReference';
import { RouteLink } from './RouteLink';
import { transcriptPath } from '../lib/routing';

interface JobRowProps {
  job: Job;
  index: number;
}

const stageLabels: Record<string, string> = {
  pending: 'Queued',
  downloading: 'Downloading',
  extracting: 'Extracting audio',
  transcribing: 'Transcribing',
  saving: 'Saving',
  completed: 'Ready to read',
  failed: 'Failed',
};

function statusColor(stage: string): string {
  if (stage === 'completed') return 'var(--status-completed)';
  if (stage === 'failed') return 'var(--status-failed)';
  if (['downloading', 'extracting', 'transcribing', 'saving'].includes(stage)) return 'var(--status-processing)';
  return 'var(--status-pending)';
}

function jobDate(dateStr: string): Date {
  // Stored job timestamps are UTC, including older values without a suffix.
  return new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(dateStr) ? dateStr : `${dateStr}Z`);
}

function timeAgo(dateStr: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - jobDate(dateStr).getTime()) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function sourceLabel(url: string): string {
  try {
    const hostname = new URL(url).hostname.toLowerCase().replace(/^www\./, '');
    if (hostname === 'youtu.be' || hostname === 'youtube.com' || hostname.endsWith('.youtube.com')) return 'YouTube';
    if (hostname === 'x.com' || hostname.endsWith('.x.com') || hostname === 'twitter.com' || hostname.endsWith('.twitter.com')) return 'X';
    return hostname;
  } catch {
    return 'Video';
  }
}

export function JobRow({ job, index }: JobRowProps) {
  const retryJob = useRetryJob();
  const deleteJob = useDeleteJob();
  const isProcessing = ['downloading', 'extracting', 'transcribing', 'saving'].includes(job.stage);
  const isClickable = job.stage === 'completed';
  const title = job.title || job.id;

  return (
    <article className={`job-row${isClickable ? ' is-ready' : ''}`}>
      <span className="job-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
      <div className="job-content">
        <div className="job-topline">
          <span className="job-source">{sourceLabel(job.url)}</span>
          <span
            className={`job-status${isProcessing ? ' is-processing' : ''}`}
            style={{ color: statusColor(job.stage) }}
          >
            <span className="job-status-dot" aria-hidden="true" />
            {stageLabels[job.stage] || job.stage}
          </span>
        </div>
        <h3 className="job-title">
          {isClickable ? (
            <RouteLink className="job-title-button" href={transcriptPath(job.id)}>
              <span>{title}</span>
              <span className="job-title-arrow" aria-hidden="true">↗</span>
            </RouteLink>
          ) : title}
        </h3>
        <p className="job-url">{job.url}</p>
        <VideoReference id={job.id} />
        {job.error && <p className="job-error">{job.error}</p>}
        {(retryJob.isError || deleteJob.isError) && (
          <p className="job-error" role="alert">{retryJob.error?.message || deleteJob.error?.message}</p>
        )}
      </div>
      <div className="job-actions">
        <time className="job-date" dateTime={jobDate(job.updated_at).toISOString()} title={jobDate(job.updated_at).toLocaleString()}>
          {timeAgo(job.updated_at)}
        </time>
        <div className="job-action-buttons">
          {job.stage === 'failed' && (
            <button
              type="button"
              onClick={() => retryJob.mutate(job.id)}
              disabled={retryJob.isPending}
              className="text-action"
            >
              {retryJob.isPending ? 'Retrying…' : 'Retry'}
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              if (confirm('Delete this job?')) deleteJob.mutate(job.id);
            }}
            disabled={deleteJob.isPending}
            className="text-action danger-action"
            aria-label={`Delete ${title}`}
          >
            {deleteJob.isPending ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </article>
  );
}
