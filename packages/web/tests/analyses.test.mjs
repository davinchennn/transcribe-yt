import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { pathToFileURL } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import * as api from '../src/api/client.ts';
import { analysisDate, analysisOptions, newestAnalyses, selectAnalysis } from '../src/lib/analyses.ts';

const require = createRequire(import.meta.url);
const compiledModules = new Map();
function componentUrl(path) {
  if (compiledModules.has(path)) return compiledModules.get(path);
  const compiled = ts.transpileModule(readFileSync(new URL(path, import.meta.url), 'utf8'), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText.replace(/(['"])(react\/jsx-runtime|react|\.\.\/lib\/analyses|\.\.\/lib\/inference|\.\.\/lib\/navigation|\.\/NavigationCanvas)\1/g, (_match, _quote, specifier) => {
    if (specifier.startsWith('react')) return JSON.stringify(pathToFileURL(require.resolve(specifier)).href);
    if (specifier === './NavigationCanvas') return JSON.stringify(componentUrl('../src/components/NavigationCanvas.tsx'));
    return JSON.stringify(new URL(`${specifier.replace('../', '../src/')}.ts`, import.meta.url).href);
  });
  const url = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`;
  compiledModules.set(path, url);
  return url;
}
const { AnalysisForm } = await import(componentUrl('../src/components/AnalysisForm.tsx'));
const { SavedAnalysisDetails } = await import(componentUrl('../src/components/SavedAnalysisDetails.tsx'));

function record(overrides = {}) {
  return {
    id: 'first', job_id: 'job', name: 'Engineering', view: 'timeline', prompt: 'Explain decisions & tradeoffs',
    status: 'completed', summary: 'The discussion follows the product decisions.', key_points: ['Prefer a simpler system.'],
    nodes: [], provider: 'kimi', model: 'kimi-model', error: null,
    created_at: '2026-10-07T12:00:00', updated_at: '2026-10-07T12:00:00', ...overrides,
  };
}
function elements(element) {
  if (!React.isValidElement(element)) return [];
  if (typeof element.type === 'function') return elements(element.type(element.props));
  return [element, ...React.Children.toArray(element.props.children).flatMap(elements)];
}
function details(analysis, overrides = {}) {
  return React.createElement(SavedAnalysisDetails, {
    analysis, providers: undefined, duration: 1000, currentTime: 0, selected: null,
    onSelect() {}, timelineSelection: [], onTimelineSelectionChange() {}, onRegenerate() {}, onDelete() {}, deleting: false,
    ...overrides,
  });
}
function form(overrides = {}) {
  return React.createElement(AnalysisForm, {
    draft: { name: '', view: 'timeline', prompt: '' }, onChange() {}, onSubmit() {}, onCancel() {},
    inferenceSettings: null, submitting: false, ready: true, ...overrides,
  });
}

test('default selection uses creation time across all visualizations and explicit IDs never fall back', () => {
  const older = record({ updated_at: '2026-10-08T00:00:00' });
  const newer = record({ id: 'newer', view: 'topics', created_at: '2026-10-07T13:00:00' });
  const input = [older, newer];
  assert.deepEqual(newestAnalyses(input).map((analysis) => analysis.id), ['newer', 'first']);
  assert.deepEqual(input, [older, newer]);
  assert.equal(selectAnalysis(input)?.id, 'newer');
  assert.equal(selectAnalysis(input, 'first')?.id, 'first');
  assert.equal(selectAnalysis(input, 'missing'), undefined);
  assert.equal(selectAnalysis(input, ''), undefined);
  assert.equal(selectAnalysis([]), undefined);
  assert.equal(selectAnalysis(input, undefined, 'timeline')?.id, 'first');
  assert.equal(selectAnalysis([newer], undefined, 'timeline')?.id, 'newer');
});

test('UTC timestamps without a zone and explicit offsets sort and display at the actual instant', () => {
  assert.equal(analysisDate('2026-10-07T12:00:00'), new Date('2026-10-07T12:00:00Z').toLocaleString());
  assert.equal(analysisDate('2026-10-07T08:00:00-04:00'), analysisDate('2026-10-07T12:00:00'));
  assert.equal(analysisDate('2026-10-07T12:00:00Z'), analysisDate('2026-10-07T12:00:00'));
  const older = record({ id: 'older', created_at: '2026-10-07T14:00:00+02:00' });
  const newer = record({ id: 'newer', created_at: '2026-10-07T12:01:00' });
  assert.deepEqual(newestAnalyses([older, newer]).map((analysis) => analysis.id), ['newer', 'older']);
});

test('analysis requests include a name, one visualization, focus prompt, and selected inference model', async () => {
  const selection = { provider: 'fireworks', model: 'accounts/fireworks/models/ember-1' };
  const options = analysisOptions('  Engineering tradeoffs  ', 'timeline', '  Emphasize technical decisions  ', selection);
  assert.deepEqual(options, { name: 'Engineering tradeoffs', view: 'timeline', prompt: 'Emphasize technical decisions', ...selection });
  assert.equal(analysisOptions('', 'timeline', '', selection).name, 'Timeline');
  assert.equal(analysisOptions(' ', 'topics', '', selection).name, 'Topics');
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, request) => {
    calls.push({ url, request });
    return { ok: true, json: async () => record({ id: 'reserved', status: 'pending' }) };
  };
  try {
    const pending = await api.createAnalysis('job ?', options);
    assert.equal(pending.status, 'pending');
    await api.regenerateAnalysis('job ?', 'analysis /?', options);
    await api.listAnalyses('job ?');
    await api.getSavedAnalysis('job ?', 'analysis /?');
    await api.deleteAnalysis('job ?', 'analysis /?');
    assert.equal(calls[0].url, '/api/jobs/job%20%3F/analyses');
    assert.equal(calls[1].url, '/api/jobs/job%20%3F/analyses/analysis%20%2F%3F/regenerate');
    assert.equal(calls[0].request.method, 'POST');
    assert.equal(calls[1].request.method, 'POST');
    assert.deepEqual(JSON.parse(calls[0].request.body), options);
    assert.deepEqual(JSON.parse(calls[1].request.body), options);
    assert.equal(calls[2].request.body, undefined);
    assert.equal(calls[3].request.body, undefined);
    assert.equal(calls[4].request.method, 'DELETE');
  } finally { globalThis.fetch = original; }
});

test('the form selects exactly one visualization and explains whole-video timeline coverage', () => {
  const changes = [];
  const rendered = elements(form({ onChange: (draft) => changes.push(draft) }));
  const select = rendered.find((element) => element.props.id === 'new-analysis-view');
  assert.equal(select.props.value, 'timeline');
  assert.deepEqual(elements(select).filter((element) => element.type === 'option').map((element) => element.props.value), ['timeline', 'topics']);
  select.props.onChange({ target: { value: 'topics' } });
  assert.deepEqual(changes, [{ name: '', view: 'topics', prompt: '' }]);
  assert.equal(rendered.find((element) => element.props.id === 'new-analysis-prompt').props.maxLength, 10000);
  const markup = renderToStaticMarkup(form());
  assert.ok(markup.includes('The timeline always covers the whole video.'));
  assert.ok(markup.includes('Create analysis'));
});

test('a new version form preserves saved fields and prevents submit before a model is available', () => {
  const draft = { name: 'Engineering', view: 'topics', prompt: 'Explain decisions', sourceId: 'previous' };
  const rendered = elements(form({ draft, ready: false }));
  assert.equal(rendered.find((element) => element.props.id === 'new-analysis-name').props.value, draft.name);
  assert.equal(rendered.find((element) => element.props.id === 'new-analysis-view').props.value, 'topics');
  assert.equal(rendered.find((element) => element.props.id === 'new-analysis-prompt').props.value, draft.prompt);
  const submit = rendered.find((element) => element.type === 'button' && element.props.type === 'submit');
  assert.equal(submit.props.disabled, true);
  assert.equal(submit.props.children, 'Create version');
  const markup = renderToStaticMarkup(form({ draft }));
  assert.ok(markup.includes('Your saved versions stay available.'));
});

test('a saved version renders its own summary, points, prompt, model, and visualization', () => {
  const analysis = record();
  const markup = renderToStaticMarkup(details(analysis));
  assert.ok(markup.includes(analysis.summary));
  assert.equal(markup.split(analysis.summary).length - 1, 1);
  assert.ok(markup.includes(analysis.key_points[0]));
  assert.ok(markup.includes('Explain decisions &amp; tradeoffs'));
  assert.ok(markup.includes('kimi-model'));
  assert.ok(markup.includes('Version saved'));
  assert.ok(markup.includes('Create another version'));
  assert.ok(markup.includes('Delete analysis'));
  assert.ok(markup.includes('navigation-canvas'));
  const legacy = renderToStaticMarkup(details(record({ view: null, name: 'General summary' })));
  assert.ok(legacy.includes('General summary'));
  assert.ok(legacy.includes(analysis.summary));
  assert.ok(!legacy.includes('navigation-canvas'));
});

test('pending records show generation status, failures expose retry as a new version, and deleting is disabled', () => {
  for (const status of ['pending', 'processing']) {
    const markup = renderToStaticMarkup(details(record({ status, summary: null })));
    assert.ok(markup.includes('role="status"'));
    assert.ok(markup.includes('Creating analysis…'));
    assert.ok(!markup.includes('navigation-canvas'));
  }
  let retries = 0;
  const failed = details(record({ status: 'failed', error: 'Provider timed out' }), { onRegenerate: () => retries += 1, deleting: true });
  const rendered = elements(failed);
  rendered.find((element) => element.type === 'button' && element.props.children === 'Retry as new version').props.onClick();
  assert.equal(retries, 1);
  assert.equal(rendered.find((element) => element.type === 'button' && element.props.children === 'Deleting…').props.disabled, true);
  assert.ok(renderToStaticMarkup(failed).includes('Provider timed out'));
});
