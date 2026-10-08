"""Inference selection crosses API/thread boundaries for independent versions."""

import asyncio
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from api import routes
from api.main import app
from transcripts.inference import resolve_inference
from transcripts.models import Analysis, AnalysisStatus, NavigationAnalysis, Stage, Transcript, Word
from transcripts.state import StateManager
from transcripts.storage.sqlite import SQLiteStorage

JOB_ID = 'abcdefghijk'


def catalog_options():
    return {
        'default_provider': 'kimi', 'default_model': 'k3',
        'providers': [
            {'id': provider, 'label': label, 'configured': True, 'default_model': model,
             'models': [{'id': model, 'name': name, 'context_length': 262144}],
             'catalog_status': 'ready', 'catalog_updated_at': '2026-10-07T00:00:00Z',
             'catalog_error': None}
            for provider, label, model, name in [
                ('kimi', 'Kimi Code', 'k3', 'K3'),
                ('fireworks', 'Fireworks AI', 'accounts/fireworks/models/live-model', 'Live model'),
            ]
        ],
    }


class InferenceRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = SQLiteStorage(str(Path(self.directory.name) / 'test.db'))
        self.state = StateManager.__new__(StateManager)
        self.state._storage = self.storage
        job = self.storage.create_job(f'https://youtube.com/watch?v={JOB_ID}')
        job.stage = Stage.COMPLETED
        self.storage.update_job(job)
        self.storage.save_transcript(JOB_ID, Transcript(video_url=job.url, title='Example',
            transcript_text='Text', words=[Word('Text', 0, 1000)]))
        for mock in (patch.object(routes, 'get_state_manager', return_value=self.state),
                     patch('transcripts.config.load_config'),
                     patch.dict(os.environ, {'FIREWORKS_API_KEY': 'fw-key', 'KIMI_CODE_API_KEY': 'kimi-key'}, clear=True)):
            mock.start()
            self.addCleanup(mock.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_catalog_exposes_configuration_without_secrets(self):
        with patch.object(routes, 'inference_options', return_value=catalog_options()) as catalog:
            response = self.client.get('/api/inference/providers')
        catalog.assert_called_once_with()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('fw-key', response.text)
        self.assertNotIn('kimi-key', response.text)
        self.assertEqual([p['id'] for p in response.json()['providers']], ['kimi', 'fireworks'])
        self.assertEqual(response.json()['providers'][1]['models'][0]['name'], 'Live model')

    def test_refresh_forces_discovery_without_starting_analysis(self):
        with patch.object(routes, 'inference_options', return_value=catalog_options()) as catalog, \
                patch.object(routes, 'run_saved_analysis') as generate:
            response = self.client.post('/api/inference/providers/refresh')
        self.assertEqual(response.status_code, 200)
        catalog.assert_called_once_with(force_refresh=True)
        generate.assert_not_called()

    def test_stale_catalog_is_returned_with_models_and_error(self):
        options = catalog_options()
        options['providers'][1].update(catalog_status='stale', catalog_error='Fireworks AI catalog unavailable')
        with patch.object(routes, 'inference_options', return_value=options):
            response = self.client.post('/api/inference/providers/refresh')
        self.assertEqual(response.status_code, 200)
        provider = response.json()['providers'][1]
        self.assertEqual(provider['catalog_status'], 'stale')
        self.assertEqual(provider['models'][0]['name'], 'Live model')
        self.assertIn('unavailable', provider['catalog_error'])

    def test_invalid_default_configuration_is_a_client_error(self):
        with patch.object(routes, 'inference_options', side_effect=ValueError('Invalid analysis provider')):
            for method, path in [('get', '/api/inference/providers'), ('post', '/api/inference/providers/refresh')]:
                self.assertEqual(getattr(self.client, method)(path).status_code, 400)

    def test_saved_versions_use_selected_inference_for_summary_and_visualization(self):
        selections = []

        def summarize(transcript, job_id, **settings):
            selection = resolve_inference()
            selections.append(('summary', selection.provider, selection.model, settings['prompt']))
            return Analysis(job_id, AnalysisStatus.COMPLETED, summary='Summary', key_points=['Point'],
                            model=selection.model, provider=selection.provider)

        def visualize(transcript, job_id, view, **settings):
            selection = resolve_inference()
            selections.append(('visualization', selection.provider, selection.model, settings['prompt']))
            return NavigationAnalysis(job_id, view, AnalysisStatus.COMPLETED,
                                      model=selection.model, provider=selection.provider)
        url = f'/api/jobs/{JOB_ID}/analyses'
        with patch('transcripts.analyses.analyze_transcript', side_effect=summarize), \
                patch('transcripts.analyses.analyze_navigation', side_effect=visualize):
            first = self.client.post(url, json={
                'name': 'Cost focus', 'view': 'timeline', 'prompt': 'Emphasize costs',
                'provider': 'fireworks', 'model': 'model-a',
            })
            self.assertEqual(first.status_code, 202, first.text)
            self.assertEqual(first.json()['provider'], 'fireworks')
            self.assertEqual(first.json()['model'], 'model-a')
            first_id = first.json()['id']
            self.assertEqual(self.client.get(f'{url}/{first_id}').json()['status'], 'completed')
            self.assertEqual(len(selections), 2)
            second = self.client.post(f'{url}/{first_id}/regenerate', json={'model': 'model-b'})
            self.assertEqual(second.status_code, 202, second.text)
            self.assertEqual(second.json()['model'], 'model-b')
            self.assertNotEqual(second.json()['id'], first_id)
        self.assertEqual(selections, [
            ('summary', 'fireworks', 'model-a', 'Emphasize costs'),
            ('visualization', 'fireworks', 'model-a', 'Emphasize costs'),
            ('summary', 'fireworks', 'model-b', 'Emphasize costs'),
            ('visualization', 'fireworks', 'model-b', 'Emphasize costs'),
        ])
        self.assertEqual(self.storage.get_saved_analysis(JOB_ID, first_id).model, 'model-a')

    def test_summary_requests_route_selected_key_and_regeneration_preserves_results(self):
        response = {'choices': [{'message': {'content': '{"summary":"Summary","key_points":["Point"]}'}}]}
        url = f'/api/jobs/{JOB_ID}/analyses'
        navigation = NavigationAnalysis(JOB_ID, 'timeline', AnalysisStatus.COMPLETED)
        with patch('transcripts.llm.urllib.request.urlopen') as request, \
                patch('transcripts.analyses.analyze_navigation', return_value=navigation):
            request.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            first = self.client.post(url, json={
                'name': 'Example', 'view': 'timeline', 'provider': 'fireworks', 'model': 'model-a',
            })
            self.assertEqual(first.status_code, 202, first.text)
            self.assertEqual(first.json()['model'], 'model-a')
            sent = request.call_args.args[0]
            self.assertEqual(sent.get_header('Authorization'), 'Bearer fw-key')
            first_id = first.json()['id']
            self.client.get(f'{url}/{first_id}')
            self.assertEqual(request.call_count, 1)
            second = self.client.post(f'{url}/{first_id}/regenerate', json={'provider': 'kimi', 'model': 'k3'})
            self.assertEqual(second.status_code, 202, second.text)
            self.assertEqual(request.call_count, 2)
            sent = request.call_args.args[0]
            self.assertEqual(sent.get_header('Authorization'), 'Bearer kimi-key')
        saved = self.storage.get_saved_analysis(JOB_ID, second.json()['id'])
        self.assertEqual((saved.provider, saved.model), ('kimi', 'k3'))
        self.assertEqual(self.storage.get_saved_analysis(JOB_ID, first_id).provider, 'fireworks')

    def test_search_uses_request_selection_and_exact_search_needs_no_key(self):
        selections = []
        def search(*args):
            selections.append(resolve_inference())
            return []
        with patch.object(routes, 'search_transcript', side_effect=search):
            response = self.client.post(f'/api/jobs/{JOB_ID}/search', json={
                'query': 'idea', 'mode': 'semantic', 'provider': 'fireworks', 'model': 'model-b'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((selections[0].provider, selections[0].model), ('fireworks', 'model-b'))
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post(f'/api/jobs/{JOB_ID}/search', json={
                'query': 'Text', 'mode': 'exact', 'provider': 'fireworks'})
        self.assertEqual(response.status_code, 200)

    def test_bad_provider_model_and_missing_key_make_no_calls(self):
        url = f'/api/jobs/{JOB_ID}/analyses'
        settings = {'name': 'Example', 'view': 'topics'}
        with patch.object(routes, 'run_saved_analysis') as analyze:
            self.assertEqual(self.client.post(url, json={**settings, 'provider': 'other'}).status_code, 422)
            self.assertEqual(self.client.post(url, json={**settings, 'model': '  '}).status_code, 400)
            with patch.dict(os.environ, {}, clear=True):
                response = self.client.post(url, json={**settings, 'provider': 'fireworks'})
                self.assertEqual(response.status_code, 400)
                self.assertIn('FIREWORKS_API_KEY', response.text)
            analyze.assert_not_called()


class NonblockingCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_does_not_block_health_requests(self):
        entered, release = threading.Event(), threading.Event()

        def slow_catalog():
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test timed out')
            return catalog_options()

        with patch.object(routes, 'inference_options', side_effect=slow_catalog):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                discovery = asyncio.create_task(client.get('/api/inference/providers'))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    health = await asyncio.wait_for(client.get('/api/health'), timeout=1)
                    self.assertEqual(health.status_code, 200)
                finally:
                    release.set()
                    response = await discovery
                self.assertEqual(response.status_code, 200)
