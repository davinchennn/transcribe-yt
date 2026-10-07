import assert from 'node:assert/strict';
import test from 'node:test';
import * as api from '../src/api/client.ts';

test('all inference actions send the selected provider and model while reads stay read-only', async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({}) };
  };
  try {
    const selection = { provider: 'fireworks', model: 'accounts/fireworks/models/ember-1' };
    await api.analyzeJob('job', selection);
    await api.createNavigation('job', 'topics', selection);
    await api.updateNavigationSummaries('job', 'topics', selection);
    await api.searchTranscript('job', 'idea', 'semantic', selection);
    for (const { options } of calls) {
      const body = JSON.parse(options.body);
      assert.equal(options.method, 'POST');
      assert.equal(body.provider, selection.provider);
      assert.equal(body.model, selection.model);
    }
    assert.equal(JSON.parse(calls[3].options.body).mode, 'semantic');
    await api.getNavigation('job', 'topics');
    await api.getInferenceProviders();
    assert.equal(calls[4].options.body, undefined);
    assert.equal(calls[5].url, '/api/inference/providers');
  } finally { globalThis.fetch = original; }
});
