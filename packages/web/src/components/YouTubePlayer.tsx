import { useEffect, useEffectEvent, useImperativeHandle, useRef, useState } from 'react';
import type { Ref } from 'react';
import { formatTime, seekMilliseconds, youtubeTimeUrl, youtubeVideoId } from '../lib/navigation';
import { loadYouTubeApi } from '../lib/youtube';
import type { YouTubePlayer as Player } from '../lib/youtube';

export interface VideoHandle {
  seek: (milliseconds: number) => void;
}

interface Props {
  url: string;
  title: string;
  selectedTime: number;
  onTimeChange: (milliseconds: number) => void;
  ref: Ref<VideoHandle>;
}

function playerError(code: number): string {
  if (code === 100) return 'This video is unavailable or private.';
  if (code === 101 || code === 150) return 'The owner has disabled embedded playback.';
  if (code === 153) return 'YouTube could not verify this embedded player.';
  return 'This video could not play here.';
}

export function YouTubePlayer({ url, title, selectedTime, onTimeChange, ref }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const player = useRef<Player | null>(null);
  const ready = useRef(false);
  const playing = useRef(false);
  const pauseAfterSeek = useRef(false);
  const pauseGuardTimeout = useRef<number | undefined>(undefined);
  const pendingSeek = useRef<number | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const videoId = youtubeVideoId(url);
  const reportTime = useEffectEvent(onTimeChange);

  useImperativeHandle(ref, () => ({
    seek(milliseconds) {
      if (!player.current || !ready.current) {
        pendingSeek.current = milliseconds;
        return;
      }
      const state = player.current.getPlayerState();
      const wasPlaying = state === 1 || (state === 3 && playing.current);
      // YouTube already preserves state=2. A guard there would pause the next
      // deliberate Play click if seeking emits no state change.
      window.clearTimeout(pauseGuardTimeout.current);
      pauseAfterSeek.current = !wasPlaying && state !== 2;
      if (pauseAfterSeek.current) {
        pauseGuardTimeout.current = window.setTimeout(() => { pauseAfterSeek.current = false; }, 1500);
      }
      seekMilliseconds(player.current, milliseconds, wasPlaying);
    },
  }), []);

  useEffect(() => {
    if (!videoId || !host.current) return;
    const container = host.current;
    let disposed = false;
    let instance: Player | null = null;
    let interval: number | undefined;
    const timeout = window.setTimeout(() => {
      if (!ready.current && !disposed) {
        setStatus('error');
        setError('The video is taking too long to load. Open the selected passage on YouTube.');
      }
    }, 20000);
    loadYouTubeApi().then((api) => {
      if (disposed) return;
      const mount = document.createElement('div');
      container.replaceChildren(mount);
      instance = new api.Player(mount, {
        videoId,
        width: '100%',
        height: '100%',
        playerVars: { origin: window.location.origin, playsinline: 1, enablejsapi: 1, rel: 0 },
        events: {
          onReady: (event) => {
            if (disposed) return;
            window.clearTimeout(timeout);
            player.current = event.target;
            ready.current = true;
            event.target.getIframe().title = title;
            setStatus('ready');
            setError(null);
            if (pendingSeek.current !== null) {
              pauseAfterSeek.current = event.target.getPlayerState() !== 2;
              pauseGuardTimeout.current = window.setTimeout(() => { pauseAfterSeek.current = false; }, 1500);
              seekMilliseconds(event.target, pendingSeek.current, false);
              pendingSeek.current = null;
            }
            interval = window.setInterval(() => {
              reportTime(event.target.getCurrentTime() * 1000);
            }, 250);
          },
          onStateChange: (event) => {
            if (disposed) return;
            if (event.data === 1 && pauseAfterSeek.current) {
              pauseAfterSeek.current = false;
              event.target.pauseVideo();
              return;
            }
            if (event.data === 1) playing.current = true;
            if (event.data === 2 || event.data === 0 || event.data === 5) {
              playing.current = false;
              pauseAfterSeek.current = false;
            }
            reportTime(event.target.getCurrentTime() * 1000);
          },
          onError: (event) => {
            if (disposed) return;
            window.clearTimeout(timeout);
            window.clearInterval(interval);
            ready.current = false;
            setStatus('error');
            setError(playerError(event.data));
          },
        },
      });
      player.current = instance;
    }).catch((reason: unknown) => {
      if (disposed) return;
      window.clearTimeout(timeout);
      setStatus('error');
      setError(reason instanceof Error ? reason.message : 'The YouTube player is unavailable.');
    });
    return () => {
      disposed = true;
      window.clearTimeout(timeout);
      window.clearInterval(interval);
      window.clearTimeout(pauseGuardTimeout.current);
      ready.current = false;
      playing.current = false;
      pauseAfterSeek.current = false;
      player.current = null;
      instance?.destroy();
      container.replaceChildren();
    };
  }, [videoId, title]);

  return (
    <section className="video-panel" aria-label="YouTube video">
      <div className="video-host" ref={host} />
      {(!videoId || status !== 'ready') && (
        <div className="video-message" role="status">
          {!videoId ? 'This URL cannot be embedded. Open the video on YouTube.' : status === 'error' ? error : 'Loading YouTube player…'}
        </div>
      )}
      <div className="video-footer">
        <span>Passage and word clicks seek the video.</span>
        <a href={youtubeTimeUrl(url, selectedTime)} target="_blank" rel="noopener noreferrer">
          Open on YouTube at {formatTime(selectedTime)} ↗
        </a>
      </div>
    </section>
  );
}
