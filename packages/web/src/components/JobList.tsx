import { useJobs } from '../hooks/useJobs';
import { JobRow } from './JobRow';

interface JobListProps {
  onSelectJob: (id: string) => void;
}

function SkeletonRow() {
  return (
    <div className="archive-skeleton-row" aria-hidden="true">
      <div className="skeleton h-3 w-16" />
      <div className="skeleton h-5 w-3/4" />
      <div className="skeleton h-3 w-1/2" />
    </div>
  );
}

export function JobList({ onSelectJob }: JobListProps) {
  const { data, isLoading, error } = useJobs();

  return (
    <section className="archive-section" aria-labelledby="archive-title" aria-busy={isLoading}>
      <div className="archive-heading">
        <div className="archive-title-group">
          <p className="section-eyebrow">Your collection</p>
          <h2 id="archive-title" className="section-title">The archive</h2>
        </div>
        {data && !error && (
          <p className="archive-count">
            <span>{data.total}</span> {data.total === 1 ? 'video' : 'videos'}
          </p>
        )}
      </div>

      {isLoading ? (
        <div role="status" aria-label="Loading your archive">
          {[...Array(3)].map((_, i) => <SkeletonRow key={i} />)}
        </div>
      ) : error ? (
        <div className="archive-error" role="alert">
          <p>We couldn’t load the archive.</p>
          <p>{error.message}</p>
        </div>
      ) : !data?.jobs.length ? (
        <div className="archive-empty">
          <span className="archive-empty-mark" aria-hidden="true">↗</span>
          <h3>Your next conversation starts here.</h3>
          <p>Add a YouTube or X video above to begin your archive.</p>
        </div>
      ) : (
        <ol className="archive-list">
          {data.jobs.map((job, i) => (
            <li key={job.id} className="archive-item">
              <JobRow job={job} index={i} onSelect={onSelectJob} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
