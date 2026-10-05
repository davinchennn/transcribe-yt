import type { Job } from '../api/client';
import { useRetryJob, useDeleteJob } from '../hooks/useJobs';

interface JobRowProps {
  job: Job;
  onSelect: (id: string) => void;
}

const stageLabels: Record<string, string> = {
  pending: 'Pending',
  downloading: 'Downloading',
  extracting: 'Extracting',
  transcribing: 'Transcribing',
  saving: 'Saving',
  completed: 'Completed',
  failed: 'Failed',
};

function statusColor(stage: string): string {
  if (stage === 'completed') return 'var(--status-completed)';
  if (stage === 'failed') return 'var(--status-failed)';
  if (['downloading', 'extracting', 'transcribing', 'saving'].includes(stage)) return 'var(--status-processing)';
  return 'var(--status-pending)';
}

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function JobRow({ job, onSelect }: JobRowProps) {
  const retryJob = useRetryJob();
  const deleteJob = useDeleteJob();

  const isProcessing = ['downloading', 'extracting', 'transcribing', 'saving'].includes(job.stage);
  const isClickable = job.stage === 'completed';

  const handleCardClick = () => {
    if (isClickable) onSelect(job.id);
  };

  return (
    <div
      onClick={handleCardClick}
      className="group rounded-xl p-5 border transition-all duration-200"
      style={{
        backgroundColor: 'var(--bg-surface)',
        borderColor: 'var(--border)',
        cursor: isClickable ? 'pointer' : 'default',
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
      {/* Title */}
      <div className="font-medium text-sm truncate mb-1" style={{ color: 'var(--text-primary)' }}>
        {job.title || job.id}
      </div>

      {/* URL preview */}
      <div className="text-xs truncate mb-4 font-mono" style={{ color: 'var(--text-muted)' }}>
        {job.url}
      </div>

      {/* Status + timestamp row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2 h-2 rounded-full ${isProcessing ? 'animate-pulse-dot' : ''}`}
            style={{ backgroundColor: statusColor(job.stage) }}
          />
          <span className="text-xs font-medium" style={{ color: statusColor(job.stage) }}>
            {stageLabels[job.stage] || job.stage}
          </span>
        </div>
        <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
          {timeAgo(job.updated_at)}
        </span>
      </div>

      {/* Error message */}
      {job.error && (
        <div className="text-xs mt-2 truncate" style={{ color: 'var(--status-failed)' }} title={job.error}>
          {job.error}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 mt-3 pt-3" style={{ borderTop: '1px solid var(--border)' }}>
        {job.stage === 'failed' && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              retryJob.mutate(job.id);
            }}
            disabled={retryJob.isPending}
            className="text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
            style={{ color: 'var(--accent)' }}
            onMouseEnter={(e) => e.currentTarget.style.color = 'var(--accent-hover)'}
            onMouseLeave={(e) => e.currentTarget.style.color = 'var(--accent)'}
          >
            Retry
          </button>
        )}
        <button
          onClick={(e) => {
            e.stopPropagation();
            if (confirm('Delete this job?')) {
              deleteJob.mutate(job.id);
            }
          }}
          disabled={deleteJob.isPending}
          className="text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer ml-auto"
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={(e) => e.currentTarget.style.color = 'var(--status-failed)'}
          onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
        >
          Delete
        </button>
      </div>
    </div>
  );
}
