"""Live catalog transports, filtering, cache isolation and failure recovery."""

import io
import json
import threading
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from transcripts import model_catalog as catalog


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


def fireworks_model(model_id, **overrides):
    return {"name": f"accounts/fireworks/models/{model_id}", "displayName": model_id.title(),
            "state": "READY", "supportsServerless": True, "kind": "HF_BASE_MODEL",
            "conversationConfig": {"template": "{{ messages }}"}, "contextLength": 32768,
            **overrides}


class ModelCatalogTests(unittest.TestCase):
    def setUp(self):
        self.cache = patch.object(catalog, '_cache', {})
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.clock = patch.object(catalog.time, 'monotonic', return_value=100.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.transport = patch('transcripts.model_catalog.urllib.request.urlopen')
        self.request = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.request.side_effect = lambda *args, **kwargs: response({'data': [
            {'id': 'k3', 'display_name': 'Kimi K3', 'context_length': 131072}]})

    def kimi(self, key='kimi-secret', base='https://api.kimi.com/coding/v1', **kwargs):
        return catalog.model_catalog('kimi', key, base, **kwargs)

    def fireworks(self, **kwargs):
        return catalog.model_catalog('fireworks', 'fw-secret', 'https://api.fireworks.ai/inference/v1', **kwargs)

    def test_kimi_auth_endpoint_and_normalization(self):
        self.request.side_effect = lambda *args, **kwargs: response({'data': [
            {'id': 'z-model', 'display_name': 'Zed', 'context_length': 8192},
            {'id': 'k3', 'display_name': ' Kimi K3 ', 'context_length': 131072},
            {'id': 'no-name', 'context_length': 0},
            {'id': 'bool-context', 'context_length': True},
            {'id': 'bad model'}, {'id': ''}, {'id': 123}, None,
            {'id': 'k3', 'display_name': 'Duplicate'}]})
        result = self.kimi(base='https://configured.example/coding/v1/')
        sent = self.request.call_args.args[0]
        self.assertEqual(sent.full_url, 'https://configured.example/coding/v1/models')
        self.assertEqual(sent.method, 'GET')
        self.assertEqual(sent.get_header('Authorization'), 'Bearer kimi-secret')
        self.assertEqual(sent.get_header('Accept'), 'application/json')
        self.assertEqual(self.request.call_args.kwargs['timeout'], catalog.REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(result['models'], [
            {'id': 'bool-context', 'name': 'bool-context', 'context_length': None},
            {'id': 'k3', 'name': 'Kimi K3', 'context_length': 131072},
            {'id': 'no-name', 'name': 'no-name', 'context_length': None},
            {'id': 'z-model', 'name': 'Zed', 'context_length': 8192}])
        self.assertEqual(result['catalog_status'], 'ready')
        self.assertIsNone(result['catalog_error'])
        self.assertTrue(result['catalog_updated_at'].endswith('Z'))
        self.assertIsNotNone(datetime.fromisoformat(result['catalog_updated_at'].replace('Z', '+00:00')).tzinfo)

    def test_fireworks_pagination_filters_to_serverless_chat(self):
        rejected = [
            fireworks_model('upload', state='UPLOADING'),
            fireworks_model('dedicated', supportsServerless=False),
            fireworks_model('base', conversationConfig=None),
            fireworks_model('embedding', kind='EMBEDDING_MODEL'),
            fireworks_model('reranker', baseModelDetails={'modelType': 'reranker'}),
            fireworks_model('whisper', baseModelDetails={'modelType': 'WhisperForConditionalGeneration'}),
            fireworks_model('speech', kind='AUDIO_MODEL'),
        ]
        pages = [
            {'models': [fireworks_model('zeta'), *rejected, None], 'nextPageToken': 'page /+ 2'},
            {'models': [fireworks_model('alpha', displayName=' Alpha Chat ', contextLength=65536),
                        fireworks_model('zeta'), fireworks_model('no-label', displayName='', contextLength=-1)]},
        ]
        self.request.side_effect = [response(page) for page in pages]
        result = self.fireworks()
        calls = self.request.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(urlsplit(calls[0].args[0].full_url)._replace(query='').geturl(), catalog.FIREWORKS_CATALOG_URL)
        self.assertEqual(parse_qs(urlsplit(calls[0].args[0].full_url).query), {'pageSize': ['200']})
        self.assertEqual(parse_qs(urlsplit(calls[1].args[0].full_url).query),
                         {'pageSize': ['200'], 'pageToken': ['page /+ 2']})
        self.assertTrue(all(call.args[0].get_header('Authorization') == 'Bearer fw-secret' for call in calls))
        self.assertEqual(result['models'], [
            {'id': 'accounts/fireworks/models/no-label', 'name': 'accounts/fireworks/models/no-label', 'context_length': None},
            {'id': 'accounts/fireworks/models/alpha', 'name': 'Alpha Chat', 'context_length': 65536},
            {'id': 'accounts/fireworks/models/zeta', 'name': 'Zeta', 'context_length': 32768}])

    def test_missing_and_placeholder_keys_skip_requests(self):
        for key in [None, '', ' ', 'your_api_key_here', ' your_api_key_here ']:
            with self.subTest(key=key):
                self.assertEqual(self.kimi(key=key, force_refresh=True), {
                    'models': [], 'catalog_status': 'unconfigured',
                    'catalog_updated_at': None, 'catalog_error': None})
        self.request.assert_not_called()
        self.assertEqual(catalog._cache, {})

    def test_cache_ttl_and_forced_refresh(self):
        initial = self.kimi()
        self.now.return_value += catalog.CATALOG_TTL_SECONDS - 1
        self.assertEqual(self.kimi(), initial)
        self.assertEqual(self.request.call_count, 1)
        self.now.return_value += 1
        self.kimi()
        self.assertEqual(self.request.call_count, 2)
        self.kimi(force_refresh=True)
        self.assertEqual(self.request.call_count, 3)

    def test_cached_catalog_is_not_mutated_by_callers(self):
        result = self.kimi()
        result['models'][0]['name'] = 'Changed'
        result['models'].clear()
        self.assertEqual(self.kimi()['models'][0]['name'], 'Kimi K3')
        self.assertEqual(self.request.call_count, 1)

    def test_empty_successful_catalog_is_cached(self):
        self.request.side_effect = lambda *args, **kwargs: response({'data': []})
        self.assertEqual(self.kimi()['models'], [])
        self.assertEqual(self.kimi()['catalog_status'], 'ready')
        self.assertEqual(self.request.call_count, 1)

    def test_cache_isolated_by_credentials_provider_and_endpoint(self):
        self.request.side_effect = [
            response({'data': [{'id': 'key-one-model'}]}),
            response({'data': [{'id': 'key-two-model'}]}),
            response({'data': [{'id': 'alternate-model'}]}),
            response({'models': [fireworks_model('chat')]}),
        ]
        first = self.kimi(key='first-secret')
        second = self.kimi(key='second-secret')
        alternate = self.kimi(key='first-secret', base='https://alternate.example/v1')
        fireworks = catalog.model_catalog('fireworks', 'first-secret', 'https://unused.example/v1')
        self.assertEqual(first['models'][0]['id'], 'key-one-model')
        self.assertEqual(second['models'][0]['id'], 'key-two-model')
        self.assertEqual(alternate['models'][0]['id'], 'alternate-model')
        self.assertEqual(fireworks['models'][0]['id'], 'accounts/fireworks/models/chat')
        self.assertEqual(self.kimi(key='first-secret'), first)
        self.assertEqual(self.request.call_count, 4)
        self.assertNotIn('first-secret', repr(catalog._cache))
        self.assertNotIn('second-secret', repr(catalog._cache))

    def test_failed_refresh_retains_catalog_and_retries_after_backoff(self):
        original = self.kimi()
        self.now.return_value += catalog.CATALOG_TTL_SECONDS
        self.request.side_effect = urllib.error.HTTPError('url', 503, 'secret', {}, io.BytesIO(b'kimi-secret'))
        failed = self.kimi()
        self.assertEqual(failed['models'], original['models'])
        self.assertEqual(failed['catalog_updated_at'], original['catalog_updated_at'])
        self.assertEqual(failed['catalog_status'], 'stale')
        self.assertEqual(failed['catalog_error'], 'Model catalog request failed (HTTP 503).')
        self.assertEqual(self.kimi(), failed)
        self.assertEqual(self.request.call_count, 2)
        self.now.return_value += catalog.FAILURE_RETRY_SECONDS
        self.request.side_effect = lambda *args, **kwargs: response({'data': [{'id': 'new-model'}]})
        recovered = self.kimi()
        self.assertEqual(recovered['catalog_status'], 'ready')
        self.assertIsNone(recovered['catalog_error'])
        self.assertEqual(recovered['models'][0]['id'], 'new-model')
        self.assertEqual(self.request.call_count, 3)

    def test_failed_forced_refresh_retries_before_previous_success_expires(self):
        self.kimi()
        self.request.side_effect = TimeoutError('kimi-secret')
        self.assertEqual(self.kimi(force_refresh=True)['catalog_status'], 'stale')
        self.now.return_value += catalog.FAILURE_RETRY_SECONDS
        self.request.side_effect = lambda *args, **kwargs: response({'data': []})
        self.assertEqual(self.kimi()['catalog_status'], 'ready')
        self.assertEqual(self.request.call_count, 3)

    def test_manual_refresh_bypasses_failure_backoff(self):
        self.request.side_effect = urllib.error.URLError('kimi-secret')
        failed = self.kimi()
        self.assertEqual(failed['catalog_status'], 'error')
        self.assertEqual(failed['models'], [])
        self.assertIsNone(failed['catalog_updated_at'])
        self.assertEqual(self.kimi(), failed)
        self.assertEqual(self.request.call_count, 1)
        self.request.side_effect = lambda *args, **kwargs: response({'data': []})
        self.assertEqual(self.kimi(force_refresh=True)['catalog_status'], 'ready')
        self.assertEqual(self.request.call_count, 2)

    def test_error_details_do_not_expose_upstream_bodies_or_keys(self):
        errors = [
            urllib.error.HTTPError('https://kimi-secret', 401, 'kimi-secret', {}, io.BytesIO(b'kimi-secret')),
            urllib.error.URLError('kimi-secret'),
            urllib.error.URLError(TimeoutError('kimi-secret')),
            TimeoutError('kimi-secret'),
            RuntimeError('kimi-secret'),
        ]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.request.side_effect = error
                result = self.kimi(force_refresh=True)
                self.assertEqual(result['catalog_status'], 'error')
                self.assertNotIn('kimi-secret', json.dumps(result))

    def test_invalid_payloads_become_safe_catalog_errors(self):
        payloads = [[], {}, {'data': {}}, 'kimi-secret']
        for payload in payloads:
            with self.subTest(payload=payload):
                self.request.side_effect = lambda *args, **kwargs: response(payload)
                result = self.kimi(force_refresh=True)
                self.assertEqual(result['catalog_status'], 'error')
                self.assertEqual(result['catalog_error'], 'The model catalog returned an invalid response.')

    def test_invalid_json_and_oversized_response(self):
        self.request.side_effect = lambda *args, **kwargs: io.BytesIO(b'not-json kimi-secret')
        self.assertEqual(self.kimi()['catalog_error'], 'The model catalog returned an invalid response.')
        with patch.object(catalog, 'MAX_RESPONSE_BYTES', 10):
            self.request.side_effect = lambda *args, **kwargs: response({'data': []})
            self.assertEqual(self.kimi(force_refresh=True)['catalog_error'], 'The model catalog response was too large.')

    def test_pagination_failure_does_not_replace_complete_catalog(self):
        self.request.side_effect = [response({'models': [fireworks_model('old')]})]
        original = self.fireworks()
        self.request.side_effect = [
            response({'models': [fireworks_model('new')], 'nextPageToken': 'two'}),
            urllib.error.URLError('fw-secret'),
        ]
        result = self.fireworks(force_refresh=True)
        self.assertEqual(result['catalog_status'], 'stale')
        self.assertEqual(result['models'], original['models'])

    def test_pagination_tokens_are_validated_and_bounded(self):
        cases = [
            ([{'models': [], 'nextPageToken': ['fw-secret']}], 'invalid response'),
            ([{'models': [], 'nextPageToken': 'again'}] * 2, 'repeated pagination tokens'),
            ([{'models': [], 'nextPageToken': 'a'}, {'models': [], 'nextPageToken': 'b'}], 'pagination limit'),
        ]
        for pages, expected in cases:
            with self.subTest(expected=expected), patch.object(catalog, 'MAX_PAGES', 2):
                self.request.side_effect = [response(page) for page in pages]
                result = self.fireworks(force_refresh=True)
                self.assertEqual(result['catalog_status'], 'error')
                self.assertIn(expected, result['catalog_error'])

    def test_concurrent_forced_refreshes_join_one_request(self):
        entered = threading.Event()
        release = threading.Event()
        waiter = threading.Event()

        def fetch(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('Test refresh was not released')
            return response({'data': [{'id': 'shared'}]})

        self.request.side_effect = fetch
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.kimi, force_refresh=True)
            try:
                self.assertTrue(entered.wait(2))
                entry = next(iter(catalog._cache.values()))
                original_wait = entry.condition.wait_for

                def observe_wait(predicate):
                    waiter.set()
                    return original_wait(predicate)

                with patch.object(entry.condition, 'wait_for', side_effect=observe_wait):
                    second = pool.submit(self.kimi, force_refresh=True)
                    self.assertTrue(waiter.wait(2))
                    release.set()
                    self.assertEqual(first.result(timeout=2), second.result(timeout=2))
            finally:
                release.set()
        self.assertEqual(self.request.call_count, 1)
