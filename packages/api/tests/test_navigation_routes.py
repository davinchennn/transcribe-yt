"""Navigation API contracts, cache isolation and explicit per-video search."""

import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from api import routes
from api.main import app
from transcripts.models import AnalysisStatus, NavigationAnalysis, Stage, Transcript, Word
from transcripts.state import StateManager
from transcripts.storage.sqlite import SQLiteStorage


JOB_ID = "abcdefghijk"
PASSAGE = {
    "id": "passage-0", "start": 1000, "end": 4000,
    "text": "Useful answers reduce costs.", "utterance_start": 0,
    "utterance_end": 0,
}
NODE = {
    "id": "section-0", "title": "Useful answers", "summary": "Measuring usefulness",
    "start": 1000, "end": 4000, "children": [], "occurrences": [PASSAGE],
}


def completed_analysis(transcript, job_id, view):
    return NavigationAnalysis(
        job_id=job_id, view=view, status=AnalysisStatus.COMPLETED,
        summary=f"{view} overview", nodes=[NODE], model="test-model",
    )


class NavigationAPITestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.storage = SQLiteStorage(str(Path(self.directory.name) / "test.db"))
        self.state = StateManager.__new__(StateManager)
        self.state._storage = self.storage
        job = self.storage.create_job(f"https://youtube.com/watch?v={JOB_ID}")
        job.stage = Stage.COMPLETED
        self.storage.update_job(job)
        words = [
            Word("Useful", 1000, 1500), Word("answers", 1500, 2200),
            Word("reduce", 2200, 2900), Word("costs.", 2900, 4000),
        ]
        self.storage.save_transcript(JOB_ID, Transcript(
            video_url=job.url, title="Example", duration=5,
            transcript_text="Useful answers reduce costs.", words=words,
        ))
        self.state_patch = patch.object(routes, "get_state_manager", return_value=self.state)
        self.state_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.state_patch.stop()
        self.directory.cleanup()

    def test_reading_uncreated_view_never_calls_llm(self):
        with patch.object(routes, "analyze_navigation") as analyze:
            response = self.client.get(f"/api/jobs/{JOB_ID}/navigation/timeline")
            detail = self.client.get(f"/api/jobs/{JOB_ID}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json())
        self.assertEqual(detail.json()["navigation"], {"timeline": None, "topics": None})
        analyze.assert_not_called()

    def test_each_view_is_created_once_and_cached_separately(self):
        with patch.object(routes, "analyze_navigation", side_effect=completed_analysis) as analyze:
            timeline = self.client.post(f"/api/jobs/{JOB_ID}/navigation/timeline")
            cached = self.client.post(f"/api/jobs/{JOB_ID}/navigation/timeline")
            self.assertIsNone(self.storage.get_navigation(JOB_ID, "topics"))
            topics = self.client.post(f"/api/jobs/{JOB_ID}/navigation/topics")
        self.assertEqual(timeline.status_code, 200)
        self.assertEqual(cached.json(), timeline.json())
        self.assertEqual(topics.json()["view"], "topics")
        self.assertEqual(analyze.call_count, 2)
        self.assertEqual([call.args[2] for call in analyze.call_args_list], ["timeline", "topics"])
        detail = self.client.get(f"/api/jobs/{JOB_ID}").json()
        self.assertEqual(detail["navigation"]["timeline"]["nodes"][0]["occurrences"][0]["start"], 1000)
        self.assertEqual(detail["navigation"]["topics"]["status"], "completed")

    def test_failed_creation_can_be_retried(self):
        failure = NavigationAnalysis(
            job_id=JOB_ID, view="timeline", status=AnalysisStatus.FAILED, error="Provider unavailable",
        )
        success = completed_analysis(None, JOB_ID, "timeline")
        with patch.object(routes, "analyze_navigation", side_effect=[failure, success]) as analyze:
            first = self.client.post(f"/api/jobs/{JOB_ID}/navigation/timeline")
            second = self.client.post(f"/api/jobs/{JOB_ID}/navigation/timeline")
        self.assertEqual(first.json()["status"], "failed")
        self.assertEqual(second.json()["status"], "completed")
        self.assertEqual(analyze.call_count, 2)

    def test_inflight_request_does_not_create_duplicate_analysis(self):
        self.assertTrue(self.storage.claim_navigation(JOB_ID, "timeline"))
        with patch.object(routes, "analyze_navigation") as analyze:
            response = self.client.post(f"/api/jobs/{JOB_ID}/navigation/timeline")
        self.assertEqual(response.status_code, 202)
        self.assertIn(response.json()["status"], ("pending", "processing"))
        analyze.assert_not_called()

    def test_unexpected_failure_releases_reservation(self):
        with patch.object(routes, "analyze_navigation", side_effect=RuntimeError("Unexpected")):
            response = self.client.post(f"/api/jobs/{JOB_ID}/navigation/timeline")
        self.assertEqual(response.json()["status"], "failed")
        self.assertTrue(self.storage.claim_navigation(JOB_ID, "timeline"))

    def test_pending_job_detail_and_creation_rejection(self):
        pending_id = "lmnopqrstuv"
        self.storage.create_job(f"https://youtube.com/watch?v={pending_id}")
        response = self.client.get(f"/api/jobs/{pending_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["transcript"])
        self.assertEqual(self.client.post(f"/api/jobs/{pending_id}/navigation/timeline").status_code, 400)

    def test_changed_source_cannot_save_stale_inflight_navigation(self):
        def replace_source(transcript, job_id, view):
            replacement = Transcript(
                video_url=transcript.video_url, title=transcript.title,
                transcript_text="Different source", words=[Word("Different", 9000, 11000)],
            )
            self.storage.save_transcript(job_id, replacement)
            return completed_analysis(transcript, job_id, view)

        with patch.object(routes, "analyze_navigation", side_effect=replace_source):
            response = self.client.post(f"/api/jobs/{JOB_ID}/navigation/timeline")
        self.assertEqual(response.status_code, 409)
        self.assertIsNone(self.storage.get_navigation(JOB_ID, "timeline"))

    def test_bad_view_and_missing_job(self):
        self.assertEqual(self.client.post(f"/api/jobs/{JOB_ID}/navigation/invalid").status_code, 422)
        self.assertEqual(self.client.post("/api/jobs/missing/navigation/timeline").status_code, 404)

    def test_search_modes_are_forwarded_and_results_keep_milliseconds(self):
        with patch.object(routes, "search_transcript", return_value=[PASSAGE]) as search:
            for mode in ("exact", "semantic"):
                response = self.client.post(f"/api/jobs/{JOB_ID}/search", json={"query": "costs", "mode": mode})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["results"][0]["start"], 1000)
                self.assertEqual(search.call_args.args[1:], ("costs", mode))

    def test_search_validation_and_provider_failure(self):
        self.assertEqual(self.client.post(f"/api/jobs/{JOB_ID}/search", json={"query": "   "}).status_code, 400)
        self.assertEqual(self.client.post(f"/api/jobs/{JOB_ID}/search", json={"query": "costs", "mode": "other"}).status_code, 422)
        with patch.object(routes, "search_transcript", side_effect=routes.LLMError("Provider unavailable")):
            response = self.client.post(f"/api/jobs/{JOB_ID}/search", json={"query": "costs", "mode": "semantic"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("Provider unavailable", response.json()["detail"])

    def test_delete_removes_both_navigation_views(self):
        for view in ("timeline", "topics"):
            self.storage.save_navigation(completed_analysis(None, JOB_ID, view))
        response = self.client.delete(f"/api/jobs/{JOB_ID}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.storage.get_navigation(JOB_ID, "timeline"))
        self.assertIsNone(self.storage.get_navigation(JOB_ID, "topics"))


class NonblockingCreationTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_remains_responsive_and_duplicate_creation_is_reserved(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(str(Path(directory) / "test.db"))
            state = StateManager.__new__(StateManager)
            state._storage = storage
            job = storage.create_job(f"https://youtube.com/watch?v={JOB_ID}")
            job.stage = Stage.COMPLETED
            storage.update_job(job)
            storage.save_transcript(JOB_ID, Transcript(
                video_url=job.url, title="Example", transcript_text="Example",
                words=[Word("Example", 0, 1000)],
            ))
            entered, release = threading.Event(), threading.Event()

            def slow_analysis(*args):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test timed out")
                return completed_analysis(*args)

            with patch.object(routes, "get_state_manager", return_value=state), patch.object(routes, "analyze_navigation", side_effect=slow_analysis) as analyze:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    creation = asyncio.create_task(client.post(f"/api/jobs/{JOB_ID}/navigation/timeline"))
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                        health = await asyncio.wait_for(client.get("/api/health"), timeout=1)
                        duplicate = await client.post(f"/api/jobs/{JOB_ID}/navigation/timeline")
                        self.assertEqual(health.status_code, 200)
                        self.assertEqual(duplicate.status_code, 202)
                        self.assertEqual(analyze.call_count, 1)
                    finally:
                        release.set()
                        response = await creation
                    self.assertEqual(response.json()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
