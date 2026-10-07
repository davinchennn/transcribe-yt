"""Shared JSON transport handles malformed output and actionable failures."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from transcripts.llm import LLMError, request_json


class TestJSONClient(unittest.TestCase):
    def response(self, content, finish_reason="stop"):
        return json.dumps({"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}).encode()

    def test_fenced_json_and_kimi_request_settings(self):
        with patch("transcripts.llm.urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = self.response('```json\n{"nodes": []}\n```')
            result = request_json("System", "User", "test-key")
        self.assertEqual(result, {"nodes": []})
        sent = request.call_args[0][0]
        self.assertEqual(sent.full_url, "https://api.kimi.com/coding/v1/chat/completions")
        self.assertEqual(sent.get_header("Authorization"), "Bearer test-key")
        payload = json.loads(sent.data)
        self.assertEqual(payload["model"], "k3")
        self.assertEqual(payload["messages"][0]["content"], "System")
        self.assertEqual(payload["messages"][1]["content"], "User")

    def test_nonobject_and_malformed_content_are_rejected(self):
        for content in ("[]", "null", "no JSON", "", None):
            with self.subTest(content=content), patch("transcripts.llm.urllib.request.urlopen") as request:
                request.return_value.__enter__.return_value.read.return_value = self.response(content)
                with self.assertRaises(LLMError):
                    request_json("System", "User", "key")

    def test_truncated_output_is_rejected_even_if_json_parses(self):
        with patch("transcripts.llm.urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = self.response("{}", "length")
            with self.assertRaisesRegex(LLMError, "output limit"):
                request_json("System", "User", "key")

    def test_missing_key_sends_no_request(self):
        with patch("transcripts.llm.inference_api_key", side_effect=ValueError("Set KIMI_CODE_API_KEY")), patch("transcripts.llm.urllib.request.urlopen") as request:
            with self.assertRaisesRegex(LLMError, "KIMI_CODE_API_KEY"):
                request_json("System", "User")
        request.assert_not_called()

    def test_network_and_http_failures_are_clear(self):
        errors = [urllib.error.URLError("offline"), urllib.error.HTTPError(
            "url", 403, "Forbidden", {}, io.BytesIO(b"Client not allowed"))]
        for error in errors:
            with self.subTest(error=error), patch("transcripts.llm.urllib.request.urlopen", side_effect=error):
                with self.assertRaises(LLMError):
                    request_json("System", "User", "key")


if __name__ == "__main__":
    unittest.main()
