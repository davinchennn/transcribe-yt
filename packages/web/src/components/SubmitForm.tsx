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
    <section className="submit-section" aria-labelledby="submit-title">
      <div className="submit-heading">
        <p className="section-eyebrow">New transcript</p>
        <h2 id="submit-title" className="section-title">Add a conversation.</h2>
        <p className="section-description">Turn a video into a transcript you can read, search, and explore.</p>
      </div>
      <form onSubmit={handleSubmit} className="submit-form">
        <div className="submit-input-row">
          <div className="submit-url-field">
            <label htmlFor="video-url" className="submit-url-label">YouTube or X video URL</label>
            <input
              id="video-url"
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Paste a video link here"
              className="submit-url-input"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              disabled={createJob.isPending}
            />
          </div>
          <button
            type="submit"
            disabled={createJob.isPending || !url.trim()}
            className="button-primary"
          >
            {createJob.isPending ? 'Submitting…' : 'Transcribe'}
            {!createJob.isPending && <span aria-hidden="true">↗</span>}
          </button>
        </div>
        <div className="submit-options">
          <label className="checkbox-option">
            <input
              type="checkbox"
              checked={keepVideo}
              onChange={(e) => setKeepVideo(e.target.checked)}
              disabled={createJob.isPending}
            />
            Keep video
          </label>
          <label className="checkbox-option">
            <input
              type="checkbox"
              checked={keepAudio}
              onChange={(e) => setKeepAudio(e.target.checked)}
              disabled={createJob.isPending}
            />
            Keep audio
          </label>
          <details className="submit-guidance">
            <summary>About video sources</summary>
            <p>
              Supports public YouTube videos and X posts. An X post uses its first video;
              use a /video/N link to choose a specific attachment. Keep video enabled
              for X playback and timestamp seeking.
            </p>
          </details>
        </div>
        {createJob.isError && <p className="form-error" role="alert">{createJob.error.message}</p>}
      </form>
    </section>
  );
}
