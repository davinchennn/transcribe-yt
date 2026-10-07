import type { InferenceOptions, InferenceProvider } from '../api/client';

export function inferenceModelName(provider: InferenceProvider | undefined, model: string | null): string {
  return provider?.models.find((item) => item.id === model)?.name
    || model?.split('/').pop()
    || 'Unknown model';
}

export function inferenceLabel(options: InferenceOptions | undefined, providerId: string | null | undefined, model: string | null): string {
  const id = providerId || 'kimi';
  const provider = options?.providers.find((item) => item.id === id);
  return `${provider?.label || id} · ${inferenceModelName(provider, model)}`;
}

export function inferenceCatalogNotice(provider: InferenceProvider | undefined): string {
  if (!provider) return 'This provider is unavailable.';
  if (!provider.configured) return `Add a ${provider.label} API key to enable analysis.`;
  if (provider.catalog_status === 'stale') return 'Could not refresh models. Showing the last saved catalog.';
  if (provider.catalog_status === 'error') return 'Could not load models. Enter a custom model ID or refresh to try again.';
  if (provider.models.length === 0) return 'No models available. Enter a custom model ID.';
  return `${provider.models.length} available model${provider.models.length === 1 ? '' : 's'}.`;
}
