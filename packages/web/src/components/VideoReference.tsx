import { useState } from 'react';

type CopyFeedback = {
  id: string;
  state: 'success' | 'error';
};

export function VideoReference({ id }: { id: string }) {
  const [feedback, setFeedback] = useState<CopyFeedback | null>(null);
  const currentFeedback = feedback?.id === id ? feedback : null;

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(id);
      setFeedback({ id, state: 'success' });
    } catch {
      setFeedback({ id, state: 'error' });
    }
  };

  return (
    <div className="video-reference">
      <span className="video-reference-label">Video ID</span>
      <code className="video-reference-id">{id}</code>
      <button
        type="button"
        className="video-reference-copy"
        aria-label={`Copy video ID ${id}`}
        onClick={copyId}
      >
        Copy
      </button>
      <span
        className="video-reference-feedback"
        role="status"
        data-state={currentFeedback?.state}
      >
        {currentFeedback?.state === 'success' && 'Copied'}
        {currentFeedback?.state === 'error' && 'Couldn’t copy. Select the ID and copy it manually.'}
      </span>
    </div>
  );
}
