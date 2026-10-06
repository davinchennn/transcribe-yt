import { useJobs } from '../hooks/useJobs';
import { JobRow } from './JobRow';

interface JobListProps {
  onSelectJob: (id: string) => void;
}

function SkeletonCard() {
  return (
    <div
      className="rounded-xl p-5 border"
      style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border)' }}
    >
      <div className="skeleton h-5 w-3/4 mb-3" />
      <div className="skeleton h-3 w-1/2 mb-4" />
      <div className="flex items-center justify-between">
        <div className="skeleton h-3 w-16" />
        <div className="skeleton h-3 w-20" />
      </div>
    </div>
  );
}

export function JobList({ onSelectJob }: JobListProps) {
  const { data, isLoading, error } = useJobs();

  if (isLoading) {
    return (
      <div>
        <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
          Recent Jobs
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-16" style={{ color: 'var(--status-failed)' }}>
        Error loading jobs: {error.message}
      </div>
    );
  }

  if (!data?.jobs.length) {
    return (
      <div className="text-center py-20">
        <p className="text-lg mb-2" style={{ color: 'var(--text-secondary)' }}>
          No transcription jobs yet
        </p>
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          Paste a YouTube or X video URL above to get started
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-baseline gap-3 mb-4">
        <h2 className="text-lg font-semibold" style={{ color: 'var(--text-secondary)' }}>
          Recent Jobs
        </h2>
        <span className="text-sm font-mono" style={{ color: 'var(--text-muted)' }}>
          {data.total}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.jobs.map((job, i) => (
          <div key={job.id} className="animate-slide-up" style={{ animationDelay: `${i * 50}ms` }}>
            <JobRow job={job} onSelect={onSelectJob} />
          </div>
        ))}
      </div>
    </div>
  );
}
