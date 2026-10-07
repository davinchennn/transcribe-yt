import { useSyncExternalStore } from 'react';
import { getRouteLocation, parseRoute, subscribeToRoute } from '../lib/routing';
import type { AppRoute } from '../lib/routing';

export function useRoute(): AppRoute {
  const location = useSyncExternalStore(subscribeToRoute, getRouteLocation, getRouteLocation);
  const queryStart = location.indexOf('?');
  return queryStart === -1
    ? parseRoute(location, '')
    : parseRoute(location.slice(0, queryStart), location.slice(queryStart));
}
