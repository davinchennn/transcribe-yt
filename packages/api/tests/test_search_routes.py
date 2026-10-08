"""Search stays scoped to a completed transcript and preserves source timings."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import routes
from api.main import app
from transcripts.models import Stage, Transcript, Word
from transcripts.state import StateManager
from transcripts.storage.sqlite import SQLiteStorage


JOB_ID = "abcdefghijk"
PASSAGE = {
    "id": "passage-0", "start": 1000, "end": 4000,
    "text": "Useful answers reduce costs.", "utterance_start": 0,
    "utterance_end": 0,
}


class SearchRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = SQLiteStorage(str(Path(self.directory.name) / "test.db"))
        self.state = StateManager.__new__(StateManager)
        self.state._storage = self.storage
        job = self.storage.create_job(f"https://youtube.com/watch?v={JOB_ID}")
        job.stage = Stage.COMPLETED
        self.storage.update_job(job)
        self.storage.save_transcript(JOB_ID, Transcript(
            video_url=job.url, title="Example", duration=5,
            transcript_text="Useful answers reduce costs.", words=[
                Word("Useful", 1000, 1500), Word("answers", 1500, 2200),
                Word("reduce", 2200, 2900), Word("costs.", 2900, 4000),
            ],
        ))
        for mock in (
            patch.object(routes, "get_state_manager", return_value=self.state),
            patch("transcripts.config.load_config"),
            patch.dict(os.environ, {"KIMI_CODE_API_KEY": "test-key"}, clear=True),
        ):
            mock.start()
            self.addCleanup(mock.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.endpoint = f"/api/jobs/{JOB_ID}/search"

    def test_search_modes_are_forwarded_and_results_keep_milliseconds(self):
        with patch.object(routes, "search_transcript", return_value=[PASSAGE]) as search:
            for mode in ("exact", "semantic"):
                response = self.client.post(self.endpoint, json={"query": "costs", "mode": mode})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["results"][0]["start"], 1000)
                self.assertEqual(search.call_args.args[1:], ("costs", mode))

    def test_search_validation_and_provider_failure(self):
        self.assertEqual(self.client.post(self.endpoint, json={"query": "   "}).status_code, 400)
        self.assertEqual(self.client.post(self.endpoint, json={"query": "costs", "mode": "other"}).status_code, 422)
        with patch.object(routes, "search_transcript", side_effect=routes.LLMError("Provider unavailable")):
            response = self.client.post(self.endpoint, json={"query": "costs", "mode": "semantic"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("Provider unavailable", response.json()["detail"])

    def test_search_requires_a_completed_transcript(self):
        with patch.object(routes, "search_transcript") as search:
            self.assertEqual(self.client.post("/api/jobs/missing/search", json={"query": "costs"}).status_code, 404)
            job = self.storage.get_job(JOB_ID)
            job.stage = Stage.PENDING
            self.storage.update_job(job)
            self.assertEqual(self.client.post(self.endpoint, json={"query": "costs"}).status_code, 400)
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
