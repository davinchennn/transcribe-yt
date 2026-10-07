"""Verify the Kimi Code request and analysis response handling without network calls."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from transcripts.analyzer import analyze_transcript
from transcripts.models import AnalysisStatus


class TestKimiCodeAnalysis(unittest.TestCase):
    def test_request_and_json_response(self):
        response = {
            "choices": [{"message": {"content": '```json\n{"summary":"A summary","key_points":["Point"]}\n```'}}]
        }
        with patch("transcripts.llm.urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            result = analyze_transcript("Transcript text", "job-1", api_key="test-key")

        req = request.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.kimi.com/coding/v1/chat/completions")
        self.assertEqual(req.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(req.get_header("User-agent"), "transcripts/0.1.0")
        payload = json.loads(req.data)
        self.assertEqual(payload["model"], "k3")
        self.assertEqual(payload["temperature"], 1)
        self.assertEqual(payload["messages"][1]["content"], "Transcript text")
        self.assertEqual(result.model, "k3")
        self.assertEqual(result.status, AnalysisStatus.COMPLETED)
        self.assertEqual(result.summary, "A summary")
        self.assertEqual(result.key_points, ["Point"])

    def test_access_rejection_is_reported(self):
        error = urllib.error.HTTPError(
            "https://api.kimi.com/coding/v1/chat/completions", 403,
            "Forbidden", {}, io.BytesIO(b'{"error":"Client not allowed"}'),
        )
        with patch("transcripts.llm.urllib.request.urlopen", side_effect=error):
            result = analyze_transcript("Text", "job-1", api_key="test-key")
        self.assertEqual(result.status, AnalysisStatus.FAILED)
        self.assertIn("403", result.error)
        self.assertIn("Client not allowed", result.error)

    def test_missing_key_does_not_send_request(self):
        with patch("transcripts.config.load_config"), patch.dict("os.environ", {}, clear=True), patch("transcripts.llm.urllib.request.urlopen") as request:
            result = analyze_transcript("Text", "job-1")
        request.assert_not_called()
        self.assertEqual(result.status, AnalysisStatus.FAILED)
        self.assertIn("KIMI_CODE_API_KEY", result.error)
