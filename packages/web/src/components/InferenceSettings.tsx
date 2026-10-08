import type { InferenceOptions, InferenceSelection } from '../api/client';
import { inferenceCatalogNotice } from '../lib/inference';

interface InferenceSettingsProps {
  options: InferenceOptions | undefined;
  inference: InferenceSelection | undefined;
  customModel: boolean;
  loading: boolean;
  refreshing: boolean;
  error?: string;
  onChange: (selection: InferenceSelection) => void;
  onCustomModelChange: (custom: boolean) => void;
  onRefresh: () => void;
  idPrefix?: string;
  heading?: string;
  description?: string;
}

export function InferenceSettings({ options, inference, customModel, loading, refreshing, error, onChange, onCustomModelChange, onRefresh, idPrefix = 'analysis', heading = 'Analysis settings', description = 'For summaries, navigation, and Meaning search.' }: InferenceSettingsProps) {
  const provider = options?.providers.find((item) => item.id === inference?.provider);
  const isCustom = customModel || !provider?.models.some((item) => item.id === inference?.model);
  const catalogError = provider?.catalog_status === 'error' || provider?.catalog_status === 'stale' || !provider?.configured;
  return <section className="inference-settings" aria-label={heading}>
    <div className="inference-heading">
      <span className="section-eyebrow">{heading}</span>
      <p className="navigation-hint">{description}</p>
    </div>
    <div className="inference-fields">
      <div className="inference-controls">
        {options && <>
          <label htmlFor={`${idPrefix}-provider`}>Provider
            <select id={`${idPrefix}-provider`} value={inference?.provider ?? ''} onChange={(event) => {
              const selected = options.providers.find((item) => item.id === event.target.value);
              if (selected) {
                onCustomModelChange(false);
                onChange({ provider: selected.id, model: selected.default_model });
              }
            }}>
              {inference && !provider && <option value={inference.provider}>{inference.provider} · Unavailable</option>}
              {options.providers.map((item) => <option key={item.id} value={item.id}>{item.label}{item.configured ? '' : ' · API key required'}</option>)}
            </select>
          </label>
          <label htmlFor={`${idPrefix}-model`}>Model
            <select id={`${idPrefix}-model`} value={isCustom ? 'custom' : inference?.model ?? ''} onChange={(event) => {
              onCustomModelChange(event.target.value === 'custom');
              if (event.target.value !== 'custom' && inference) onChange({ provider: inference.provider, model: event.target.value });
            }}>
              {provider?.models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
              <option value="custom">Custom model…</option>
            </select>
          </label>
          {isCustom && <label className="inference-custom-model" htmlFor={`custom-${idPrefix}-model`}>Custom model ID
            <input id={`custom-${idPrefix}-model`} value={inference?.model ?? ''} onChange={(event) => {
              if (inference) onChange({ provider: inference.provider, model: event.target.value });
            }} placeholder="Enter a model ID" autoCapitalize="none" spellCheck={false} />
          </label>}
        </>}
        <button type="button" className="nav-button compact inference-refresh" disabled={loading || refreshing} onClick={onRefresh}>{refreshing ? 'Refreshing models…' : 'Refresh models'}</button>
      </div>
      {loading && <p className="navigation-hint" role="status">Loading models…</p>}
      {error && <p className="nav-error" role="alert">{error}</p>}
      {options && !refreshing && <p className={catalogError ? 'nav-error' : 'navigation-hint'} role={catalogError ? 'status' : undefined} title={provider?.catalog_error || (provider?.catalog_updated_at ? `Models updated ${new Date(provider.catalog_updated_at).toLocaleString()}` : undefined)}>{inferenceCatalogNotice(provider)}</p>}
    </div>
  </section>;
}
