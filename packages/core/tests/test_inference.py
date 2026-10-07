"""Provider selection, credential isolation, persistence and request scoping."""

import io
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from transcripts.analyzer import analyze_transcript
from transcripts.inference import InferenceSelection, inference_options, inference_scope, resolve_inference
from transcripts.llm import LLMError, request_json
from transcripts.models import Analysis, AnalysisStatus, NavigationAnalysis
from transcripts.storage.sqlite import SQLiteStorage


class InferenceTests(unittest.TestCase):
    def setUp(self):
        self.config = patch('transcripts.config.load_config')
        self.config.start()
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.config.stop)
        self.addCleanup(self.env.stop)

    def test_defaults_and_explicit_selection(self):
        self.assertEqual(resolve_inference(), InferenceSelection('kimi', 'k3'))
        with patch.dict(os.environ, {'ANALYSIS_PROVIDER': 'fireworks', 'FIREWORKS_MODEL': 'custom-model'}):
            self.assertEqual(resolve_inference(), InferenceSelection('fireworks', 'custom-model'))
            self.assertEqual(resolve_inference('kimi'), InferenceSelection('kimi', 'k3'))
            self.assertEqual(resolve_inference('fireworks', 'override').model, 'override')
        for provider, model in [('other', None), ('kimi', ''), ('fireworks', 'bad model')]:
            with self.subTest(provider=provider, model=model), self.assertRaises(ValueError):
                resolve_inference(provider, model)

    def test_options_never_expose_keys(self):
        catalog = {'models': [{'id': 'discovered-model', 'name': 'Discovered model', 'context_length': 8192}],
                   'catalog_status': 'ready', 'catalog_updated_at': '2026-10-07T12:00:00Z', 'catalog_error': None}
        with patch.dict(os.environ, {'FIREWORKS_API_KEY': 'secret-key'}), \
                patch('transcripts.inference.model_catalog', return_value=catalog) as discovery:
            options = inference_options()
        self.assertNotIn('secret-key', json.dumps(options))
        self.assertFalse(options['providers'][0]['configured'])
        self.assertTrue(options['providers'][1]['configured'])
        self.assertEqual(options['providers'][1]['models'], catalog['models'])
        self.assertEqual(options['providers'][1]['catalog_status'], 'ready')
        self.assertEqual(discovery.call_args.args, ('fireworks', 'secret-key', 'https://api.fireworks.ai/inference/v1'))
        self.assertEqual(discovery.call_args.kwargs, {'force_refresh': False})

    def test_options_force_refresh_keeps_custom_defaults_out_of_catalog(self):
        catalog = {'models': [], 'catalog_status': 'unconfigured',
                   'catalog_updated_at': None, 'catalog_error': None}
        with patch.dict(os.environ, {'FIREWORKS_MODEL': 'custom-model'}), \
                patch('transcripts.inference.model_catalog', return_value=catalog) as discovery:
            options = inference_options(force_refresh=True)
        self.assertEqual(options['providers'][1]['default_model'], 'custom-model')
        self.assertEqual(options['providers'][1]['models'], [])
        self.assertTrue(all(call.kwargs['force_refresh'] for call in discovery.call_args_list))

    def test_fireworks_request_and_analysis_metadata(self):
        data = {'choices': [{'message': {'content': '{"summary":"Summary","key_points":["Point"]}'}}]}
        with patch.dict(os.environ, {'FIREWORKS_API_KEY': 'fw-key', 'KIMI_CODE_API_KEY': 'kimi-key'}), patch('transcripts.llm.urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value = json.dumps(data).encode()
            result = analyze_transcript('Text', 'job', provider='fireworks', model='accounts/fireworks/models/ember-1')
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, 'https://api.fireworks.ai/inference/v1/chat/completions')
        self.assertEqual(sent.get_header('Authorization'), 'Bearer fw-key')
        self.assertEqual(json.loads(sent.data)['model'], 'accounts/fireworks/models/ember-1')
        self.assertEqual(result.provider, 'fireworks')
        self.assertEqual(result.model, 'accounts/fireworks/models/ember-1')
        self.assertEqual(result.status, AnalysisStatus.COMPLETED)

    def test_missing_fireworks_key_does_not_fall_back_to_kimi(self):
        with patch.dict(os.environ, {'KIMI_CODE_API_KEY': 'kimi-key'}), patch('transcripts.llm.urllib.request.urlopen') as request:
            with self.assertRaisesRegex(LLMError, 'FIREWORKS_API_KEY'):
                request_json('System', 'User', provider='fireworks')
            request.assert_not_called()

    def test_http_errors_redact_key(self):
        error = urllib.error.HTTPError('url', 401, 'Unauthorized', {}, io.BytesIO(b'bad secret-key'))
        with patch('transcripts.llm.urllib.request.urlopen', side_effect=error):
            with self.assertRaises(LLMError) as raised:
                request_json('System', 'User', 'secret-key', provider='fireworks')
        self.assertIn('Fireworks AI API error 401', str(raised.exception))
        self.assertNotIn('secret-key', str(raised.exception))

    def test_scopes_are_isolated_and_reset_after_failure(self):
        def read(selection):
            with inference_scope(selection):
                return [resolve_inference() for _ in range(10)]
        choices = [InferenceSelection('kimi', 'k3'), InferenceSelection('fireworks', 'fw-model')]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(read, choices))
        self.assertEqual(results, [[choice] * 10 for choice in choices])
        with self.assertRaises(RuntimeError):
            with inference_scope(choices[1]):
                raise RuntimeError('failed')
        self.assertEqual(resolve_inference(), choices[0])

    def test_legacy_schema_migration_and_model_cache_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.db'
            storage = SQLiteStorage(str(path))
            job = storage.create_job('https://youtube.com/watch?v=abcdefghijk')
            storage.save_analysis(Analysis(job.id, AnalysisStatus.COMPLETED, model='k3', provider='kimi'))
            storage.save_navigation(NavigationAnalysis(job.id, 'timeline', AnalysisStatus.COMPLETED, model='k3', provider='kimi'))
            # Recreate the pre-provider schema, then reopen using normal migration.
            with sqlite3.connect(path) as conn:
                conn.execute('ALTER TABLE analyses DROP COLUMN provider')
                conn.execute('ALTER TABLE navigation_analyses DROP COLUMN provider')
            storage = SQLiteStorage(str(path))
            self.assertEqual(storage.get_analysis(job.id).provider, 'kimi')
            self.assertEqual(storage.get_navigation(job.id, 'timeline').provider, 'kimi')
            self.assertFalse(storage.claim_navigation(job.id, 'timeline', 'kimi', 'k3'))
            self.assertTrue(storage.claim_navigation(job.id, 'timeline', 'fireworks', 'fw-model'))
            reserved = storage.get_navigation(job.id, 'timeline')
            self.assertEqual((reserved.provider, reserved.model), ('fireworks', 'fw-model'))
            self.assertFalse(storage.claim_navigation(job.id, 'timeline', 'kimi', 'k3'))
            storage.save_navigation(NavigationAnalysis(job.id, 'timeline', AnalysisStatus.COMPLETED, model='fw-model', provider='fireworks'))
            storage.save_analysis(Analysis(job.id, AnalysisStatus.COMPLETED, model='fw-model', provider='fireworks'))
            self.assertEqual(storage.get_analysis(job.id).provider, 'fireworks')
            self.assertEqual(storage.get_navigation(job.id, 'timeline').provider, 'fireworks')
            self.assertFalse(storage.claim_navigation(job.id, 'timeline', 'fireworks', 'fw-model'))
            self.assertIsNone(storage.get_navigation(job.id, 'topics'))
