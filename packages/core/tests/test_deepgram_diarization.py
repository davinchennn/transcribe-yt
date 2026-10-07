"""Verify diarization parameters sent through the installed Deepgram SDK."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from deepgram import DeepgramClient

from transcripts.transcriber import DeepgramTranscriber


class TestDeepgramDiarization(unittest.TestCase):
    def test_diarization_requests(self):
        for source in ("file", "url"):
            for options, expected in (
                ({}, "v2"),
                ({"diarize": False}, None),
                ({"diarize_model": "v1"}, "v1"),
            ):
                with self.subTest(source=source, options=options):
                    requests = []

                    def respond(request):
                        requests.append(request)
                        return httpx.Response(202, json={"request_id": "test-request"})

                    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                        transcriber = DeepgramTranscriber.__new__(DeepgramTranscriber)
                        transcriber.client = DeepgramClient(
                            api_key="test-key", httpx_client=client,
                            telemetry_opt_out=True,
                        )
                        with patch.object(transcriber, "_build_transcript") as build:
                            if source == "file":
                                with tempfile.TemporaryDirectory() as directory:
                                    audio = Path(directory) / "audio.mp3"
                                    audio.write_bytes(b"test audio")
                                    transcriber.transcribe_file(str(audio), **options)
                            else:
                                transcriber.transcribe_url("https://example.com/audio.mp3", **options)
                            build.assert_called_once()

                    self.assertEqual(len(requests), 1)
                    query = requests[0].url.params
                    self.assertEqual(query.get("diarize_model"), expected)
                    self.assertNotIn("diarize", query)
                    self.assertEqual(query.get("model"), "nova-2")
                    self.assertEqual(query.get("utterances"), "true")
