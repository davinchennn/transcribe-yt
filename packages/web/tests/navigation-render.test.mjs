import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { pathToFileURL } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/components/NavigationCanvas.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
  .replace(/(['"])react\/jsx-runtime\1/g, JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href))
  .replace(/(['"])\.\.\/lib\/navigation\1/g, JSON.stringify(new URL('../src/lib/navigation.ts', import.meta.url).href));
const { NavigationCanvas } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

const summaries = {
  demand: 'Consumer demand spending savings wages employment inflation household budgets disposable income retail sales purchasing power confidence economic growth recession interest rates.',
  rates: 'Interest rates financing costs asset prices discount rates credit availability investment borrowing mortgage payments debt refinancing capital markets liquidity lending decisions.',
  tiny: 'A short cached summary remains readable without regeneration.',
};
const passage = { id: 'rates-passage', start: 21000, end: 22000, text: 'Borrowing costs affect demand.', utterance_start: 0, utterance_end: 0 };
const leaf = { id: 'rates', title: 'Borrowing costs', summary: summaries.rates, start: 21000, end: 22000, children: [], occurrences: [passage] };
const demand = { id: 'demand', title: 'Household demand', summary: summaries.demand, start: 20000, end: 40000, children: [leaf], occurrences: [] };
const tiny = { id: 'tiny', title: 'Short aside', summary: summaries.tiny, start: 50000, end: 50050, children: [], occurrences: [] };
const root = { id: 'chapter', title: 'Economic outlook', summary: 'Chapter summary', start: 0, end: 100000, children: [demand, tiny], occurrences: [] };

function props(view = 'timeline', overrides = {}) {
  return {
    analysis: { job_id: 'job', view, status: 'completed', summary: null, nodes: [root] },
    duration: 100000,
    currentTime: 0,
    selected: null,
    onSelect() {},
    timelineSelection: [],
    onTimelineSelectionChange() {},
    ...overrides,
  };
}

// These components are pure, so expanding their elements also exposes the real
// click handlers without adding a browser or a second React testing runtime.
function elements(element) {
  if (!React.isValidElement(element)) return [];
  if (typeof element.type === 'function') return elements(element.type(element.props));
  return [element, ...React.Children.toArray(element.props.children).flatMap(elements)];
}

const hasClass = (element, name) => element.props.className?.split(' ').includes(name);

test('Timeline shows cached summaries inside subtopic tiles at every visible hierarchy level', () => {
  const rendered = elements(React.createElement(NavigationCanvas, props('timeline', { timelineSelection: ['demand'] })));
  const summaryElements = rendered.filter((element) => hasClass(element, 'subtopic-summary'));
  assert.deepEqual(summaryElements.map((element) => element.props.children), [summaries.demand, summaries.tiny, summaries.rates]);
  assert.equal(rendered.filter((element) => hasClass(element, 'subtopic-track')).length, 2);
  const markup = renderToStaticMarkup(React.createElement(NavigationCanvas, props('timeline', { timelineSelection: ['demand'] })));
  assert.ok(markup.includes(`<span class="subtopic-summary">${summaries.tiny}</span>`));
  assert.ok(markup.includes(`<span class="subtopic-summary">${summaries.rates}</span>`));
});

test('Selected summaries stay fully readable outside horizontal timing tracks, including tiny topics and ancestors', () => {
  const rendered = elements(React.createElement(NavigationCanvas, props('timeline', { timelineSelection: ['demand', 'rates'] })));
  const details = rendered.filter((element) => hasClass(element, 'selected-topic-summary'));
  assert.equal(details.length, 2);
  assert.deepEqual(details.map((detail) => elements(detail).find((element) => element.type === 'p').props.children), [summaries.demand, summaries.rates]);
  const tinyRendered = elements(React.createElement(NavigationCanvas, props('timeline', { timelineSelection: ['tiny'] })));
  const fullSummary = tinyRendered.find((element) => hasClass(element, 'selected-topic-summary'));
  assert.equal(elements(fullSummary).find((element) => element.type === 'p').props.children, summaries.tiny);
  const rootContainer = NavigationCanvas(props('timeline', { timelineSelection: ['tiny'] }));
  const bandsElement = React.Children.toArray(rootContainer.props.children).find((element) => typeof element.type === 'function');
  const bands = bandsElement.type(bandsElement.props);
  const siblings = React.Children.toArray(bands.props.children);
  assert.equal(siblings[0].props['aria-label'], 'Selected subtopic summaries');
  assert.equal(siblings[1].props.className, 'timeline-scroll');
});

test('Taller summary tiles preserve exact durations and selection does not seek playback', () => {
  const selections = [];
  const seeks = [];
  const rendered = elements(React.createElement(NavigationCanvas, props('timeline', {
    timelineSelection: ['demand'],
    onTimelineSelectionChange: (ids) => selections.push(ids),
    onSelect: (selectedPassage) => seeks.push(selectedPassage),
  })));
  const topic = rendered.find((element) => element.type === 'button' && element.props['aria-label']?.startsWith('Select Household demand,'));
  assert.equal(topic.props.style.left, '20%');
  assert.equal(topic.props.style.width, '20%');
  const deeper = rendered.find((element) => element.type === 'button' && element.props['aria-label']?.startsWith('Select Borrowing costs,'));
  assert.equal(deeper.props.style.left, '5%');
  assert.equal(deeper.props.style.width, '5%');
  deeper.props.onClick();
  assert.deepEqual(selections, [['demand', 'rates']]);
  assert.deepEqual(seeks, []);
  const selected = elements(React.createElement(NavigationCanvas, props('timeline', {
    timelineSelection: selections[0],
    onSelect: (selectedPassage) => seeks.push(selectedPassage),
  })));
  const passageButton = selected.find((element) => element.type === 'button' && element.props['aria-label']?.startsWith('Go to Borrowing costs passage'));
  passageButton.props.onClick();
  assert.deepEqual(seeks, [passage]);
});

test('Topics wraps visible summaries for all subtopic depths and preserves occurrence seeking', () => {
  const seeks = [];
  const rendered = elements(React.createElement(NavigationCanvas, props('topics', { onSelect: (selectedPassage) => seeks.push(selectedPassage) })));
  const summaryElements = rendered.filter((element) => hasClass(element, 'subtopic-summary'));
  assert.deepEqual(summaryElements.map((element) => element.props.children), [summaries.demand, summaries.rates, summaries.tiny]);
  assert.ok(summaryElements.every((element) => element.type === 'p'));
  const occurrence = rendered.find((element) => element.type === 'button' && hasClass(element, 'topic-occurrence'));
  assert.equal(occurrence.props.style.left, '21%');
  assert.equal(occurrence.props.style.width, '1%');
  occurrence.props.onClick();
  assert.deepEqual(seeks, [passage]);
});

test('Stale hierarchy selections never display summaries from unrelated branches', () => {
  const rendered = elements(React.createElement(NavigationCanvas, props('timeline', { timelineSelection: ['tiny', 'rates'] })));
  const details = rendered.filter((element) => hasClass(element, 'selected-topic-summary'));
  assert.equal(details.length, 1);
  assert.equal(elements(details[0]).find((element) => element.type === 'p').props.children, summaries.tiny);
});

test('Long videos give substantial subtopics readable widths without distorting their time geometry', () => {
  const duration = 38 * 60000;
  const subtopics = Array.from({ length: 8 }, (_, index) => ({
    ...tiny,
    id: `long-topic-${index}`,
    start: index * 200000,
    end: index * 200000 + 78000 + index * 6000,
  }));
  const rendered = elements(React.createElement(NavigationCanvas, props('timeline', {
    duration,
    analysis: { ...props().analysis, nodes: [{ ...root, end: duration, children: subtopics }] },
  })));
  const canvasWidth = rendered.find((element) => hasClass(element, 'timeline-content')).props.style.minWidth;
  assert.equal(canvasWidth, Math.ceil(180 * duration / 78000));
  const tiles = rendered.filter((element) => element.type === 'button' && hasClass(element, 'topic-tile'));
  assert.ok(canvasWidth * Number.parseFloat(tiles[0].props.style.width) / 100 >= 180);
  assert.equal(tiles[1].props.style.left, `${200000 / duration * 100}%`);
  assert.equal(tiles[1].props.style.width, `${84000 / duration * 100}%`);
});

test('Seconds-long asides do not force a massive timeline, and canvas expansion is bounded', () => {
  const duration = 38 * 60000;
  const children = [{ ...demand, start: 0, end: duration / 2 }, { ...tiny, start: 1500000, end: 1501000 }];
  const rendered = elements(React.createElement(NavigationCanvas, props('timeline', {
    duration,
    analysis: { ...props().analysis, nodes: [{ ...root, end: duration, children }] },
  })));
  assert.equal(rendered.find((element) => hasClass(element, 'timeline-content')).props.style.minWidth, 780);
  const bounded = elements(React.createElement(NavigationCanvas, props('timeline', {
    duration,
    analysis: { ...props().analysis, nodes: [{ ...root, end: duration, children: [{ ...demand, start: 0, end: 30000 }] }] },
  })));
  assert.equal(bounded.find((element) => hasClass(element, 'timeline-content')).props.style.minWidth, 6000);
});
