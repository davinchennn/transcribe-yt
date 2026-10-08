import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { pathToFileURL } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import * as api from '../src/api/client.ts';
import { inferenceLabel } from '../src/lib/inference.ts';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/components/InferenceSettings.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
  .replace(/(['"])react\/jsx-runtime\1/g, JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href))
  .replace(/(['"])\.\.\/lib\/inference\1/g, JSON.stringify(new URL('../src/lib/inference.ts', import.meta.url).href));
const { InferenceSettings } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

const selectedModel = { id: 'accounts/fireworks/models/ember-1', name: 'Ember One', context_length: 131072 };
const catalog = {
  default_provider: 'fireworks',
  default_model: selectedModel.id,
  providers: [{
    id: 'fireworks', label: 'Fireworks AI', configured: true, default_model: selectedModel.id,
    models: [selectedModel], catalog_status: 'ready', catalog_updated_at: '2026-10-07T10:00:00Z', catalog_error: null,
  }],
};

function props(overrides = {}) {
  return {
    options: catalog,
    inference: { provider: 'fireworks', model: selectedModel.id },
    customModel: false, loading: false, refreshing: false,
    onChange() {}, onCustomModelChange() {}, onRefresh() {},
    ...overrides,
  };
}

function elements(element) {
  if (!React.isValidElement(element)) return [];
  if (typeof element.type === 'function') return elements(element.type(element.props));
  return [element, ...React.Children.toArray(element.props.children).flatMap(elements)];
}

test('all inference actions send the selected provider and model while reads stay read-only', async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({}) };
  };
  try {
    const selection = { provider: 'fireworks', model: 'accounts/fireworks/models/ember-1' };
    await api.createAnalysis('job', { name: 'Topics', view: 'topics', prompt: 'Explain tradeoffs', ...selection });
    await api.regenerateAnalysis('job', 'saved', selection);
    await api.searchTranscript('job', 'idea', 'semantic', selection);
    for (const { options } of calls) {
      const body = JSON.parse(options.body);
      assert.equal(options.method, 'POST');
      assert.equal(body.provider, selection.provider);
      assert.equal(body.model, selection.model);
    }
    assert.equal(JSON.parse(calls[2].options.body).mode, 'semantic');
    await api.listAnalyses('job');
    await api.getSavedAnalysis('job', 'saved');
    await api.getInferenceProviders();
    assert.equal(calls[3].url, '/api/jobs/job/analyses');
    assert.equal(calls[3].options.body, undefined);
    assert.equal(calls[4].url, '/api/jobs/job/analyses/saved');
    assert.equal(calls[4].options.body, undefined);
    assert.equal(calls[5].url, '/api/inference/providers');
  } finally { globalThis.fetch = original; }
});

test('catalog reads and explicit refresh return discovered names and model metadata', async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => catalog };
  };
  try {
    assert.deepEqual(await api.getInferenceProviders(), catalog);
    assert.deepEqual(await api.refreshInferenceProviders(), catalog);
    assert.equal(calls[0].url, '/api/inference/providers');
    assert.equal(calls[0].options.method, undefined);
    assert.equal(calls[1].url, '/api/inference/providers/refresh');
    assert.equal(calls[1].options.method, 'POST');
    assert.equal(calls[1].options.body, undefined);
  } finally { globalThis.fetch = original; }
});

test('model choices display discovered names and send model IDs only when selected', () => {
  const changes = [];
  const rendered = elements(React.createElement(InferenceSettings, props({ onChange: (value) => changes.push(value) })));
  const modelSelect = rendered.find((element) => element.props.id === 'analysis-model');
  assert.equal(modelSelect.props.value, selectedModel.id);
  const modelOption = rendered.find((element) => element.type === 'option' && element.props.value === selectedModel.id);
  assert.equal(modelOption.props.children, 'Ember One');
  assert.deepEqual(changes, []);
  modelSelect.props.onChange({ target: { value: selectedModel.id } });
  assert.deepEqual(changes, [{ provider: 'fireworks', model: selectedModel.id }]);
  assert.equal(inferenceLabel(catalog, 'fireworks', selectedModel.id), 'Fireworks AI · Ember One');
  assert.equal(inferenceLabel(catalog, 'fireworks', 'accounts/fireworks/models/retired'), 'Fireworks AI · retired');
});

test('catalog changes keep remembered and custom IDs visible without replacing the selection', () => {
  for (const model of ['accounts/fireworks/models/retired', 'my-custom-deployment']) {
    const changes = [];
    const rendered = elements(React.createElement(InferenceSettings, props({
      inference: { provider: 'fireworks', model },
      onChange: (value) => changes.push(value),
    })));
    assert.equal(rendered.find((element) => element.props.id === 'analysis-model').props.value, 'custom');
    assert.equal(rendered.find((element) => element.props.id === 'custom-analysis-model').props.value, model);
    assert.deepEqual(changes, []);
  }
});

test('refresh and catalog errors preserve cached model options and selected IDs', () => {
  const stale = { ...catalog, providers: [{ ...catalog.providers[0], catalog_status: 'stale', catalog_error: 'Catalog timed out' }] };
  let refreshes = 0;
  const changes = [];
  const settings = props({
    options: stale,
    error: 'Could not refresh models: Connection lost',
    onRefresh: () => { refreshes += 1; },
    onChange: (value) => changes.push(value),
  });
  const rendered = elements(React.createElement(InferenceSettings, settings));
  assert.equal(rendered.find((element) => element.props.id === 'analysis-model').props.value, selectedModel.id);
  assert.ok(rendered.some((element) => element.type === 'option' && element.props.value === selectedModel.id));
  rendered.find((element) => element.type === 'button').props.onClick();
  assert.equal(refreshes, 1);
  assert.deepEqual(changes, []);
  const markup = renderToStaticMarkup(React.createElement(InferenceSettings, settings));
  assert.ok(markup.includes('Showing the last saved catalog.'));
  assert.ok(markup.includes('Connection lost'));
});

test('loading and unavailable catalogs offer clear status and a custom model entry', () => {
  const loading = elements(React.createElement(InferenceSettings, props({ options: undefined, inference: undefined, loading: true })));
  assert.equal(loading.find((element) => element.type === 'button').props.disabled, true);
  assert.ok(loading.some((element) => element.props.role === 'status' && element.props.children === 'Loading models…'));
  const options = { ...catalog, providers: [{ ...catalog.providers[0], models: [], catalog_status: 'error', catalog_error: 'Catalog timed out' }] };
  const failed = renderToStaticMarkup(React.createElement(InferenceSettings, props({ options })));
  assert.ok(failed.includes('Enter a custom model ID or refresh to try again.'));
  assert.ok(failed.includes(`value="${selectedModel.id}"`));
});
