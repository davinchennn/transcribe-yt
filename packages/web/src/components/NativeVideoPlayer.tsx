import { useEffect, useEffectEvent, useImperativeHandle, useRef, useState } from 'react';
import type { Ref } from 'react';
import { getVideoUrl } from '../api/client';
import { formatTime } from '../lib/navigation';
import { connectNativeVideo, nativeVideoError } from '../lib/video';
import type { NativeVideoController } from '../lib/video';
import type { VideoHandle } from './YouTubePlayer';

interface Props {
  jobId: string;
  url: string;
  title: string;
  available: boolean;
  selectedTime: number;
  onTimeChange: (milliseconds: number) => void;
  ref: Ref<VideoHandle>;
}

function NativeVideoSession({ jobId, url, title, available, selectedTime, onTimeChange, ref }: Props) {
  const media = useRef<HTMLVideoElement>(null);
  const controller = useRef<NativeVideoController | null>(null);
  const pendingSeek = useRef<number | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const reportTime = useEffectEvent(onTimeChange);

  useImperativeHandle(ref, () => ({
    seek(milliseconds) {
      if (controller.current) controller.current.seek(milliseconds);
      else if (available) pendingSeek.current = milliseconds;
    },
  }), [available]);

  useEffect(() => {
    if (!available || !media.current) return;
    const instance = connectNativeVideo(media.current, reportTime);
    controller.current = instance;
    if (pendingSeek.current !== null) {
      instance.seek(pendingSeek.current);
      pendingSeek.current = null;
    }
    const timeout = window.setTimeout(() => {
      if (media.current?.readyState === 0) {
        setStatus('error');
        setError('The saved video is taking too long to load. Reload this page to try again. The transcript is still available.');
      }
    }, 20000);
    return () => {
      window.clearTimeout(timeout);
      instance.dispose();
      controller.current = null;
      pendingSeek.current = null;
    };
  }, [available]);

  return (
    <section className="video-panel" aria-label="X video">
      <div className="video-host">
        {available && <video
          ref={media}
          src={getVideoUrl(jobId)}
          controls
          playsInline
          preload="metadata"
          aria-label={title}
          onLoadedMetadata={() => { setStatus('ready'); setError(null); }}
          onError={(event) => { setStatus('error'); setError(nativeVideoError(event.currentTarget.error?.code)); }}
        />}
      </div>
      {(!available || status !== 'ready') && <div className="video-message" role="status">
        {!available
          ? 'The saved video is unavailable. It may not have been kept or may have been removed. You can still read and search the transcript.'
          : status === 'error' ? error : 'Loading saved X video…'}
      </div>}
      <div className="video-footer">
        <span>{available && status !== 'error' ? 'Passage and word clicks seek the video.' : 'Transcript navigation is available.'} Selected: {formatTime(selectedTime)}</span>
        <a href={url} target="_blank" rel="noopener noreferrer">Open post on X ↗</a>
      </div>
    </section>
  );
}

export function NativeVideoPlayer(props: Props) {
  return <NativeVideoSession key={`${props.jobId}:${props.available}`} {...props} />;
}
