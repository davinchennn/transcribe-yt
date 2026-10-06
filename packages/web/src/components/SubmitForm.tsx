import { useState } from 'react';
import { useCreateJob } from '../hooks/useJobs';

export function SubmitForm() {
  const [url, setUrl] = useState('');
  const [keepVideo, setKeepVideo] = useState(true);
  const [keepAudio, setKeepAudio] = useState(true);
  const createJob = useCreateJob();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    createJob.mutate(
      { url, keep_video: keepVideo, keep_audio: keepAudio },
      { onSuccess: () => setUrl('') }
    );
  };

  return (
    <form onSubmit={handleSubmit} className="mb-10">
      <div
        className="rounded-xl p-5 border"
        style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex gap-3 mb-4">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste YouTube or X video URL..."
            aria-label="YouTube or X video URL"
            className="flex-1 px-4 py-2.5 rounded-lg text-sm border outline-none transition-colors"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              borderColor: 'var(--border)',
              color: 'var(--text-primary)',
            }}
            onFocus={(e) => e.currentTarget.style.borderColor = 'var(--accent)'}
            onBlur={(e) => e.currentTarget.style.borderColor = 'var(--border)'}
            disabled={createJob.isPending}
          />
          <button
            type="submit"
            disabled={createJob.isPending || !url.trim()}
            className="px-6 py-2.5 rounded-lg text-sm font-medium text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            style={{ backgroundColor: 'var(--accent)' }}
            onMouseEnter={(e) => {
              if (!e.currentTarget.disabled) e.currentTarget.style.backgroundColor = 'var(--accent-hover)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--accent)';
            }}
          >
            {createJob.isPending ? 'Submitting...' : 'Go'}
          </button>
        </div>
        <div className="flex items-center gap-6">
          <label className="flex items-center gap-2 cursor-pointer text-sm" style={{ color: 'var(--text-secondary)' }}>
            <input
              type="checkbox"
              checked={keepVideo}
              onChange={(e) => setKeepVideo(e.target.checked)}
              className="w-4 h-4 rounded accent-[#818cf8]"
              disabled={createJob.isPending}
            />
            Keep video
          </label>
          <label className="flex items-center gap-2 cursor-pointer text-sm" style={{ color: 'var(--text-secondary)' }}>
            <input
              type="checkbox"
              checked={keepAudio}
              onChange={(e) => setKeepAudio(e.target.checked)}
              className="w-4 h-4 rounded accent-[#818cf8]"
              disabled={createJob.isPending}
            />
            Keep audio
          </label>
          {createJob.isError && (
            <span className="text-sm ml-auto" style={{ color: 'var(--status-failed)' }}>
              {createJob.error.message}
            </span>
          )}
        </div>
        <p className="mt-3 text-xs" style={{ color: 'var(--text-muted)' }}>
          Public YouTube videos and X posts. An X post uses its first video; use a /video/N link to choose a specific media attachment. Keep video enabled for X playback and timestamp seeking.
        </p>
      </div>
    </form>
  );
}
