"""Inference selection crosses API/thread boundaries and respects saved caches."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api import routes
from api.main import app
from transcripts.inference import resolve_inference
from transcripts.models import AnalysisStatus, NavigationAnalysis, Stage, Transcript, Word
from transcripts.state import StateManager
from transcripts.storage.sqlite import SQLiteStorage

JOB_ID = 'abcdefghijk'


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
        response = self.client.get('/api/inference/providers')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('fw-key', response.text)
        self.assertNotIn('kimi-key', response.text)
        self.assertEqual([p['id'] for p in response.json()['providers']], ['kimi', 'fireworks'])

    def test_navigation_changes_model_only_on_explicit_request(self):
        def analyze(transcript, job_id, view):
            selection = resolve_inference()
            return NavigationAnalysis(job_id, view, AnalysisStatus.COMPLETED,
                                      model=selection.model, provider=selection.provider)
        url = f'/api/jobs/{JOB_ID}/navigation/timeline'
        with patch.object(routes, 'analyze_navigation', side_effect=analyze) as request:
            first = self.client.post(url, json={'provider': 'fireworks', 'model': 'model-a'})
            self.assertEqual(first.json()['provider'], 'fireworks')
            self.assertEqual(first.json()['model'], 'model-a')
            cached = self.client.post(url, json={'provider': 'fireworks', 'model': 'model-a'})
            self.assertEqual(cached.json(), first.json())
            self.assertEqual(self.client.post(url).json(), first.json())
            second = self.client.post(url, json={'provider': 'fireworks', 'model': 'model-b'})
            self.assertEqual(second.json()['model'], 'model-b')
            self.assertEqual(request.call_count, 2)
        self.assertIsNone(self.storage.get_navigation(JOB_ID, 'topics'))

    def test_summary_routes_selected_model_and_reuses_cache(self):
        response = {'choices': [{'message': {'content': '{"summary":"Summary","key_points":["Point"]}'}}]}
        url = f'/api/jobs/{JOB_ID}/analyze'
        with patch('transcripts.llm.urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            first = self.client.post(url, json={'provider': 'fireworks', 'model': 'model-a'})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()['model'], 'model-a')
            sent = request.call_args.args[0]
            self.assertEqual(sent.get_header('Authorization'), 'Bearer fw-key')
            self.client.post(url, json={'provider': 'fireworks', 'model': 'model-a'})
            self.assertEqual(request.call_count, 1)
            self.client.post(url, json={'provider': 'kimi', 'model': 'k3'})
            self.assertEqual(request.call_count, 2)
        saved = self.storage.get_analysis(JOB_ID)
        self.assertEqual((saved.provider, saved.model), ('kimi', 'k3'))

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
        url = f'/api/jobs/{JOB_ID}/navigation/topics'
        with patch.object(routes, 'analyze_navigation') as analyze:
            self.assertEqual(self.client.post(url, json={'provider': 'other'}).status_code, 422)
            self.assertEqual(self.client.post(url, json={'model': '  '}).status_code, 400)
            with patch.dict(os.environ, {}, clear=True):
                response = self.client.post(url, json={'provider': 'fireworks'})
                self.assertEqual(response.status_code, 400)
                self.assertIn('FIREWORKS_API_KEY', response.text)
            analyze.assert_not_called()
