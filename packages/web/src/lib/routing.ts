import type { NavigationView } from '../api/client';

export type AppRoute =
  | { page: 'home' }
  | { page: 'transcript'; jobId: string; view?: NavigationView; analysisId?: string }
  | { page: 'not-found' };

export function parseRoute(pathname: string, search: string): AppRoute {
  if (pathname === '/') return { page: 'home' };

  const match = /^\/jobs\/([^/]+)\/?$/.exec(pathname);
  if (!match) return { page: 'not-found' };

  try {
    const jobId = decodeURIComponent(match[1]);
    if (!jobId || jobId.includes('/')) return { page: 'not-found' };
    const params = new URLSearchParams(search);
    if (params.has('analysis')) return { page: 'transcript', jobId, analysisId: params.get('analysis')! };
    const view = params.get('view');
    return { page: 'transcript', jobId, ...(view === 'topics' || view === 'timeline' ? { view } : {}) };
  } catch {
    return { page: 'not-found' };
  }
}

export function analysisPath(jobId: string, analysisId?: string): string {
  return `/jobs/${encodeURIComponent(jobId)}${analysisId !== undefined ? `?analysis=${encodeURIComponent(analysisId)}` : ''}`;
}

export function transcriptPath(jobId: string, view: NavigationView = 'timeline'): string {
  return `/jobs/${encodeURIComponent(jobId)}${view === 'topics' ? '?view=topics' : ''}`;
}

const subscribers = new Set<() => void>();

function notifyRouteChange() {
  for (const callback of [...subscribers]) callback();
}

export function subscribeToRoute(callback: () => void): () => void {
  if (subscribers.size === 0) window.addEventListener('popstate', notifyRouteChange);
  subscribers.add(callback);
  return () => {
    subscribers.delete(callback);
    if (subscribers.size === 0) window.removeEventListener('popstate', notifyRouteChange);
  };
}

export function getRouteLocation(): string {
  return typeof window === 'undefined' ? '/' : window.location.pathname + window.location.search;
}

export function navigate(to: string): void {
  const url = new URL(to, window.location.href);
  if (url.href === window.location.href) return;
  window.history.pushState(null, '', url.href);
  notifyRouteChange();
}
