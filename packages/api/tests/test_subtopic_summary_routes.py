"""Explicit subtopic-summary updates preserve cached navigation and source data."""

import asyncio
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from api import routes
from api.main import app
from transcripts.llm import LLMError
from transcripts.models import AnalysisStatus, NavigationAnalysis, Stage, Transcript, Word
from transcripts.state import StateManager
from transcripts.storage.sqlite import SQLiteStorage


JOB_ID = "abcdefghijk"
SUMMARY = "Engineers share infrastructure and automate production deployments to reduce operating costs."
OLD_SUMMARY = "An older summary that describes shared infrastructure and automated production deployments while preserving reliable software delivery across several engineering teams and product groups."
assert 0 < len(SUMMARY.split()) < 20
assert len(OLD_SUMMARY.split()) > 20


def saved_navigation(view="timeline"):
    passage = {
        "id": "passage-1", "start": 1000, "end": 3000,
        "text": "Engineers share infrastructure and automate production deployments.",
        "utterance_start": 0, "utterance_end": 0,
    }
    child = {
        "id": "topic-2", "title": "Infrastructure sharing", "summary": OLD_SUMMARY,
        "start": 1000, "end": 3000, "occurrences": [passage], "children": [],
    }
    root = {
        "id": "topic-1", "title": "Engineering", "summary": "Chapter overview.",
        "start": 1000, "end": 3000, "occurrences": [passage], "children": [child],
    }
    return NavigationAnalysis(
        job_id=JOB_ID, view=view, status=AnalysisStatus.COMPLETED,
        summary="Video overview", nodes=[root], model="test-model",
    )


def updated_summaries(transcript, analysis):
    updated = copy.deepcopy(analysis)
    updated.nodes[0]["children"][0]["summary"] = SUMMARY
    return updated


class SummaryAPITestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.storage = SQLiteStorage(str(Path(self.directory.name) / "test.db"))
        self.state = StateManager.__new__(StateManager)
        self.state._storage = self.storage
        job = self.storage.create_job(f"https://youtube.com/watch?v={JOB_ID}")
        job.stage = Stage.COMPLETED
        self.storage.update_job(job)
        self.transcript = Transcript(
            video_url=job.url, title="Engineering", transcript_text="Engineers share infrastructure.",
            words=[Word("Engineers", 1000, 1500), Word("share", 1500, 2000), Word("infrastructure.", 2000, 3000)],
        )
        self.storage.save_transcript(JOB_ID, self.transcript)
        for view in ("timeline", "topics"):
            self.storage.save_navigation(saved_navigation(view))
        self.state_patch = patch.object(routes, "get_state_manager", return_value=self.state)
        self.state_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.state_patch.stop()
        self.directory.cleanup()

    def endpoint(self, view="timeline"):
        return f"/api/jobs/{JOB_ID}/navigation/{view}/summaries"

    def test_reading_saved_views_does_not_generate_summaries(self):
        with patch.object(routes, "summarize_subtopics") as summarize:
            detail = self.client.get(f"/api/jobs/{JOB_ID}")
            view = self.client.get(f"/api/jobs/{JOB_ID}/navigation/timeline")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(view.status_code, 200)
        summarize.assert_not_called()

    def test_refresh_changes_only_subtopic_summaries_and_preserves_other_view(self):
        before = self.storage.get_navigation(JOB_ID, "timeline")
        other = self.storage.get_navigation(JOB_ID, "topics").to_dict()
        with patch.object(routes, "summarize_subtopics", side_effect=updated_summaries) as summarize:
            response = self.client.post(self.endpoint())
        self.assertEqual(response.status_code, 200, response.text)
        summarize.assert_called_once()
        self.assertEqual(response.json()["nodes"][0]["children"][0]["summary"], SUMMARY)
        after = self.storage.get_navigation(JOB_ID, "timeline")
        expected = updated_summaries(self.transcript, before).to_dict()
        expected["updated_at"] = after.updated_at
        self.assertEqual(after.to_dict(), expected)
        self.assertEqual(self.storage.get_navigation(JOB_ID, "topics").to_dict(), other)
        self.assertEqual(self.storage.get_transcript(JOB_ID).words, self.transcript.words)

    def test_compliant_summaries_return_cached_view_without_another_request(self):
        self.storage.save_navigation(updated_summaries(self.transcript, saved_navigation()))
        before = self.storage.get_navigation(JOB_ID, "timeline").to_dict()
        with patch.object(routes, "summarize_subtopics") as summarize:
            response = self.client.post(self.endpoint())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nodes"][0]["children"][0]["summary"], SUMMARY)
        self.assertEqual(self.storage.get_navigation(JOB_ID, "timeline").to_dict(), before)
        summarize.assert_not_called()

    def test_provider_failure_preserves_completed_navigation_and_can_retry(self):
        before = self.storage.get_navigation(JOB_ID, "timeline").to_dict()
        with patch.object(routes, "summarize_subtopics", side_effect=LLMError("Provider unavailable")):
            response = self.client.post(self.endpoint())
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.storage.get_navigation(JOB_ID, "timeline").to_dict(), before)
        with patch.object(routes, "summarize_subtopics", side_effect=updated_summaries):
            self.assertEqual(self.client.post(self.endpoint()).status_code, 200)

    def test_changed_navigation_cannot_be_overwritten_by_stale_summaries(self):
        def replace_view(transcript, analysis):
            replacement = copy.deepcopy(analysis)
            replacement.nodes[0]["title"] = "Replacement chapter"
            self.storage.save_navigation(replacement)
            return updated_summaries(transcript, analysis)

        with patch.object(routes, "summarize_subtopics", side_effect=replace_view):
            response = self.client.post(self.endpoint())
        self.assertEqual(response.status_code, 409)
        current = self.storage.get_navigation(JOB_ID, "timeline")
        self.assertEqual(current.nodes[0]["title"], "Replacement chapter")
        self.assertEqual(current.nodes[0]["children"][0]["summary"], OLD_SUMMARY)

    def test_changed_transcript_cannot_receive_stale_summaries(self):
        def replace_source(transcript, analysis):
            self.storage.save_transcript(JOB_ID, Transcript(
                video_url=transcript.video_url, title=transcript.title,
                transcript_text="A replacement source", words=[Word("Replacement", 4000, 5000)],
            ))
            return updated_summaries(transcript, analysis)

        with patch.object(routes, "summarize_subtopics", side_effect=replace_source):
            response = self.client.post(self.endpoint())
        self.assertEqual(response.status_code, 409)
        self.assertIsNone(self.storage.get_navigation(JOB_ID, "timeline"))

    def test_missing_or_incomplete_view_is_rejected(self):
        self.assertEqual(self.client.post("/api/jobs/missing/navigation/timeline/summaries").status_code, 404)
        self.assertEqual(self.client.post(self.endpoint("invalid")).status_code, 422)
        pending = saved_navigation()
        pending.status = AnalysisStatus.PROCESSING
        self.storage.save_navigation(pending)
        self.assertEqual(self.client.post(self.endpoint()).status_code, 400)


class ConcurrentSummaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_updates_share_work_and_health_remains_responsive(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(str(Path(directory) / "test.db"))
            state = StateManager.__new__(StateManager)
            state._storage = storage
            job = storage.create_job(f"https://youtube.com/watch?v={JOB_ID}")
            job.stage = Stage.COMPLETED
            storage.update_job(job)
            storage.save_transcript(JOB_ID, Transcript(
                video_url=job.url, title="Engineering", words=[Word("Infrastructure", 1000, 2000)],
            ))
            storage.save_navigation(saved_navigation())
            entered, release = threading.Event(), threading.Event()

            def slow_summary(*args):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test timed out")
                return updated_summaries(*args)

            with patch.object(routes, "get_state_manager", return_value=state), patch.object(routes, "summarize_subtopics", side_effect=slow_summary) as summarize:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    endpoint = f"/api/jobs/{JOB_ID}/navigation/timeline/summaries"
                    first = asyncio.create_task(client.post(endpoint))
                    duplicate = None
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                        duplicate = asyncio.create_task(client.post(endpoint))
                        health = await asyncio.wait_for(client.get("/api/health"), timeout=1)
                        self.assertEqual(health.status_code, 200)
                    finally:
                        release.set()
                        responses = await asyncio.gather(first, duplicate) if duplicate else [await first]
                    self.assertTrue(all(response.status_code == 200 for response in responses))
                    self.assertEqual(summarize.call_count, 1)
                    self.assertEqual(responses[0].json(), responses[1].json())


if __name__ == "__main__":
    unittest.main()
