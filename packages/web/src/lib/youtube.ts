export interface YouTubePlayer {
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  playVideo(): void;
  pauseVideo(): void;
  getPlayerState(): number;
  getCurrentTime(): number;
  getIframe(): HTMLIFrameElement;
  destroy(): void;
}

interface PlayerEvent { target: YouTubePlayer; data: number }

interface YouTubeApi {
  Player: new (element: HTMLElement, options: {
    videoId: string;
    width: string;
    height: string;
    playerVars: Record<string, string | number>;
    events: {
      onReady: (event: PlayerEvent) => void;
      onStateChange: (event: PlayerEvent) => void;
      onError: (event: PlayerEvent) => void;
    };
  }) => YouTubePlayer;
}

declare global {
  interface Window {
    YT?: YouTubeApi;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<YouTubeApi> | null = null;

export function loadYouTubeApi(): Promise<YouTubeApi> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (apiPromise) return apiPromise;
  apiPromise = new Promise((resolve, reject) => {
    const previousReady = window.onYouTubeIframeAPIReady;
    const timeout = window.setTimeout(() => {
      apiPromise = null;
      reject(new Error('The YouTube player did not load. Open the selected passage on YouTube.'));
    }, 15000);
    window.onYouTubeIframeAPIReady = () => {
      window.clearTimeout(timeout);
      if (window.YT?.Player) resolve(window.YT);
      else reject(new Error('The YouTube player is unavailable.'));
      previousReady?.();
    };
    if (!document.querySelector('script[src="https://www.youtube.com/iframe_api"]')) {
      const script = document.createElement('script');
      script.src = 'https://www.youtube.com/iframe_api';
      script.async = true;
      script.addEventListener('error', () => {
        window.clearTimeout(timeout);
        apiPromise = null;
        script.remove();
        reject(new Error('The YouTube player could not load. Open the selected passage on YouTube.'));
      }, { once: true });
      document.head.appendChild(script);
    }
  });
  return apiPromise;
}
