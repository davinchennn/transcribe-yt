export function isXVideoUrl(value: string): boolean {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^(www|mobile|m)\./, '');
    return ['http:', 'https:'].includes(url.protocol)
      && ['x.com', 'twitter.com'].includes(host)
      && /^\/(?:[^/]+\/status|i\/web\/status|statuses)\/\d+(?:\/video\/[1-9]\d*)?\/?$/.test(url.pathname);
  } catch {
    return false;
  }
}

export interface NativeVideo {
  currentTime: number;
  duration: number;
  readyState: number;
  addEventListener: (type: string, listener: EventListener) => void;
  removeEventListener: (type: string, listener: EventListener) => void;
}

export interface NativeVideoController {
  seek: (milliseconds: number) => void;
  dispose: () => void;
}

export function connectNativeVideo(video: NativeVideo, onTimeChange: (milliseconds: number) => void): NativeVideoController {
  let pendingSeek: number | null = null;
  let disposed = false;
  const report = () => {
    if (!disposed && Number.isFinite(video.currentTime)) onTimeChange(video.currentTime * 1000);
  };
  const seek = (milliseconds: number) => {
    if (disposed || !Number.isFinite(milliseconds)) return;
    if (video.readyState === 0) {
      pendingSeek = milliseconds;
      return;
    }
    const target = Math.max(0, milliseconds) / 1000;
    // Setting currentTime preserves the native player's playing or paused state.
    video.currentTime = Number.isFinite(video.duration) ? Math.min(target, Math.max(0, video.duration)) : target;
    pendingSeek = null;
    report();
  };
  const metadata = () => {
    if (pendingSeek !== null) seek(pendingSeek);
    else report();
  };
  video.addEventListener('loadedmetadata', metadata);
  video.addEventListener('timeupdate', report);
  video.addEventListener('seeked', report);
  return {
    seek,
    dispose() {
      disposed = true;
      pendingSeek = null;
      video.removeEventListener('loadedmetadata', metadata);
      video.removeEventListener('timeupdate', report);
      video.removeEventListener('seeked', report);
    },
  };
}

export function nativeVideoError(code?: number): string {
  if (code === 3) return 'This browser could not decode the saved video. The transcript is still available.';
  if (code === 4) return 'The saved video is unavailable or uses a format this browser cannot play. The transcript is still available.';
  if (code === 1) return 'Video loading was interrupted. Reload this page to try again. The transcript is still available.';
  return 'The saved video could not be loaded. It may have been removed or the connection failed. The transcript is still available.';
}
