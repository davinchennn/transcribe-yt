import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { pathToFileURL } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { analysisPath, getRouteLocation, navigate, parseRoute, subscribeToRoute, transcriptPath } from '../src/lib/routing.ts';

const require = createRequire(import.meta.url);

async function importComponent(path) {
  const compiled = ts.transpileModule(readFileSync(new URL(path, import.meta.url), 'utf8'), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
    .replace(/(['"])react\/jsx-runtime\1/g, JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href))
    .replace(/(['"])react\1/g, JSON.stringify(pathToFileURL(require.resolve('react')).href))
    .replace(/(['"])\.\.\/lib\/routing\1/g, JSON.stringify(new URL('../src/lib/routing.ts', import.meta.url).href));
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
}

const { RouteLink } = await importComponent('../src/components/RouteLink.tsx');
const { useRoute } = await importComponent('../src/hooks/useRoute.ts');

class FakeWindow extends EventTarget {
  constructor(url) {
    super();
    this.location = new URL(url);
    this.entries = [this.location.href];
    this.index = 0;
    const browser = this;
    this.history = {
      get length() { return browser.entries.length; },
      pushState(_state, _unused, to) {
        browser.location = new URL(to, browser.location.href);
        browser.entries.splice(browser.index + 1);
        browser.entries.push(browser.location.href);
        browser.index += 1;
      },
      go(delta) {
        const index = browser.index + delta;
        if (index < 0 || index >= browser.entries.length) return;
        browser.index = index;
        browser.location = new URL(browser.entries[index]);
        browser.dispatchEvent(new Event('popstate'));
      },
      back() { this.go(-1); },
      forward() { this.go(1); },
    };
  }
}

function withWindow(url, callback) {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const browser = new FakeWindow(url);
  Object.defineProperty(globalThis, 'window', { value: browser, configurable: true, writable: true });
  try {
    callback(browser);
  } finally {
    if (original) Object.defineProperty(globalThis, 'window', original);
    else delete globalThis.window;
  }
}

test('routes reconstruct the requested job and view from the URL on first load or refresh', () => {
  withWindow('https://app.example/jobs/job-123?view=topics#passage', () => {
    assert.equal(getRouteLocation(), '/jobs/job-123?view=topics');
    assert.deepEqual(parseRoute(window.location.pathname, window.location.search), {
      page: 'transcript', jobId: 'job-123', view: 'topics',
    });
    function RouteProbe() {
      return React.createElement('output', null, JSON.stringify(useRoute()));
    }
    const markup = renderToStaticMarkup(React.createElement(RouteProbe));
    assert.ok(markup.includes('&quot;page&quot;:&quot;transcript&quot;'));
    assert.ok(markup.includes('&quot;jobId&quot;:&quot;job-123&quot;'));
    assert.ok(markup.includes('&quot;view&quot;:&quot;topics&quot;'));
  });
});

test('transcript paths escape job IDs and only topics requires a view query', () => {
  const jobId = 'job ?&=#% café';
  const path = transcriptPath(jobId);
  assert.equal(path, '/jobs/job%20%3F%26%3D%23%25%20caf%C3%A9');
  assert.equal(transcriptPath(jobId, 'timeline'), path);
  assert.equal(transcriptPath(jobId, 'topics'), `${path}?view=topics`);
  assert.deepEqual(parseRoute(path, ''), { page: 'transcript', jobId });
  assert.deepEqual(parseRoute(`${path}/`, '?view=topics'), { page: 'transcript', jobId, view: 'topics' });
});

test('absent or invalid views leave selection at the newest analysis and explicit legacy views remain supported', () => {
  for (const search of ['', '?view=', '?view=unknown', '?other=topics']) {
    assert.deepEqual(parseRoute('/jobs/a', search), { page: 'transcript', jobId: 'a' });
  }
  assert.deepEqual(parseRoute('/jobs/a', '?view=timeline'), { page: 'transcript', jobId: 'a', view: 'timeline' });
  assert.deepEqual(parseRoute('/', '?view=topics'), { page: 'home' });
});

test('unknown paths, missing IDs, decoded slashes and malformed escapes show not-found', () => {
  for (const path of ['', '//', '/home', '/jobs', '/jobs/', '/jobs/a/b', '/jobs/a//', '/jobs/%', '/jobs/%zz', '/jobs/%E0%A4%A', '/jobs/%2F', '/jobs/a%2fb']) {
    assert.deepEqual(parseRoute(path, ''), { page: 'not-found' }, path);
  }
});

test('navigation notifies subscribers and browser Back and Forward restore the job and view', () => {
  withWindow('https://app.example/', (browser) => {
    const locations = [];
    const cleanup = subscribeToRoute(() => locations.push(getRouteLocation()));
    try {
      navigate(transcriptPath('a'));
      navigate(transcriptPath('a', 'topics'));
      navigate('/jobs/b');
      browser.history.back();
      assert.deepEqual(parseRoute(browser.location.pathname, browser.location.search), { page: 'transcript', jobId: 'a', view: 'topics' });
      browser.history.back();
      browser.history.back();
      assert.deepEqual(parseRoute(browser.location.pathname, browser.location.search), { page: 'home' });
      browser.history.forward();
      browser.history.forward();
      assert.deepEqual(locations, ['/jobs/a', '/jobs/a?view=topics', '/jobs/b', '/jobs/a?view=topics', '/jobs/a', '/', '/jobs/a', '/jobs/a?view=topics']);
    } finally {
      cleanup();
    }
  });
});

test('the same URL creates no duplicate entry or notification, and hashes stay outside route snapshots', () => {
  withWindow('https://app.example/jobs/a?view=topics#selected', (browser) => {
    let notifications = 0;
    const cleanup = subscribeToRoute(() => notifications += 1);
    try {
      navigate('/jobs/a?view=topics#selected');
      navigate('https://app.example/jobs/a?view=topics#selected');
      assert.equal(browser.history.length, 1);
      assert.equal(notifications, 0);
      navigate('/jobs/a?view=topics#other');
      assert.equal(browser.location.hash, '#other');
      assert.equal(getRouteLocation(), '/jobs/a?view=topics');
      assert.equal(browser.history.length, 2);
    } finally {
      cleanup();
    }
  });
});

test('unsubscribing one listener retains other listeners and cleanup removes popstate notifications', () => {
  withWindow('https://app.example/', (browser) => {
    let first = 0;
    let second = 0;
    const cleanupFirst = subscribeToRoute(() => first += 1);
    const cleanupSecond = subscribeToRoute(() => second += 1);
    try {
      navigate('/jobs/a');
      cleanupFirst();
      browser.history.back();
      assert.equal(first, 1);
      assert.equal(second, 2);
      cleanupSecond();
      browser.history.forward();
      assert.equal(second, 2);
    } finally {
      cleanupFirst();
      cleanupSecond();
    }
  });
});

function clickLink(props, overrides = {}) {
  const link = RouteLink(props);
  assert.equal(link.type, 'a');
  assert.equal(link.props.href, props.href);
  const event = {
    currentTarget: {
      href: new URL(props.href, window.location.href).href,
      target: props.target ?? '',
      rel: props.rel ?? '',
      hasAttribute: (name) => name === 'download' && props.download != null,
    },
    button: 0,
    defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; },
    ...overrides,
  };
  link.props.onClick(event);
  return event;
}

test('route links retain real hrefs and intercept ordinary same-window local clicks', () => {
  withWindow('https://app.example/', (browser) => {
    let updates = 0;
    const cleanup = subscribeToRoute(() => updates += 1);
    try {
      const event = clickLink({ href: '/jobs/a?view=topics#selected', target: '_self', children: 'Open job' });
      assert.equal(event.defaultPrevented, true);
      assert.equal(browser.location.href, 'https://app.example/jobs/a?view=topics#selected');
      assert.equal(updates, 1);
    } finally {
      cleanup();
    }
  });
});

test('modified clicks, middle clicks, new-window, download and external links retain browser behavior', () => {
  withWindow('https://app.example/', (browser) => {
    for (const overrides of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
      assert.equal(clickLink({ href: '/jobs/a' }, overrides).defaultPrevented, false);
    }
    for (const props of [
      { href: '/jobs/a', target: '_blank' },
      { href: '/jobs/a', target: 'other-window' },
      { href: '/jobs/a', download: '' },
      { href: '/jobs/a', rel: 'noopener EXTERNAL' },
      { href: 'https://other.example/jobs/a' },
      { href: 'mailto:example@app.example' },
    ]) assert.equal(clickLink(props).defaultPrevented, false);
    assert.equal(browser.history.length, 1);
    assert.equal(browser.location.pathname, '/');
  });
});

test('route links honor caller click handlers and already-prevented events', () => {
  withWindow('https://app.example/', (browser) => {
    let calls = 0;
    const event = clickLink({ href: '/jobs/a', onClick(event) { calls += 1; event.preventDefault(); } });
    assert.equal(calls, 1);
    assert.equal(event.defaultPrevented, true);
    clickLink({ href: '/jobs/a' }, { defaultPrevented: true });
    assert.equal(browser.history.length, 1);
  });
});


test('analysis links escape IDs, restore the exact saved version, and take precedence over legacy views', () => {
  const id = 'analysis ?&=#% café';
  const path = analysisPath('job ?', id);
  const url = new URL(path, 'https://app.example');
  assert.equal(path, '/jobs/job%20%3F?analysis=analysis%20%3F%26%3D%23%25%20caf%C3%A9');
  assert.deepEqual(parseRoute(url.pathname, url.search), { page: 'transcript', jobId: 'job ?', analysisId: id });
  assert.deepEqual(parseRoute('/jobs/a', '?analysis=saved&view=topics'), { page: 'transcript', jobId: 'a', analysisId: 'saved' });
  assert.deepEqual(parseRoute('/jobs/a', '?analysis='), { page: 'transcript', jobId: 'a', analysisId: '' });
  assert.equal(analysisPath('a'), '/jobs/a');
});

test('browser Back and Forward restore selected saved analyses within one video', () => {
  withWindow('https://app.example/jobs/a', (browser) => {
    const locations = [];
    const cleanup = subscribeToRoute(() => locations.push(getRouteLocation()));
    try {
      navigate(analysisPath('a', 'first'));
      navigate(analysisPath('a', 'second'));
      browser.history.back();
      assert.deepEqual(parseRoute(browser.location.pathname, browser.location.search), { page: 'transcript', jobId: 'a', analysisId: 'first' });
      browser.history.forward();
      assert.deepEqual(parseRoute(browser.location.pathname, browser.location.search), { page: 'transcript', jobId: 'a', analysisId: 'second' });
      assert.deepEqual(locations, ['/jobs/a?analysis=first', '/jobs/a?analysis=second', '/jobs/a?analysis=first', '/jobs/a?analysis=second']);
    } finally { cleanup(); }
  });
});
