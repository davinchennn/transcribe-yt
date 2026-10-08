"""Named analysis versions are isolated, explicit, and scoped to their video."""

import asyncio
import copy
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
from transcripts.analyses import AnalysisConflictError
from transcripts.models import Analysis, AnalysisStatus, NavigationAnalysis, Stage, Transcript, Word
from transcripts.state import StateManager
from transcripts.storage.sqlite import SQLiteStorage


JOB_ID = "abcdefghijk"
OTHER_ID = "lmnopqrstuv"
NODE = {
    "id": "chapter-0", "title": "Infrastructure", "summary": "Shared infrastructure reduces costs.",
    "start": 0, "end": 2000, "children": [], "occurrences": [{
        "id": "passage-0", "start": 0, "end": 2000, "text": "Shared infrastructure.",
        "utterance_start": 0, "utterance_end": 0,
    }],
}
SETTINGS = {
    "name": "Cost focus", "view": "timeline", "prompt": "Emphasize costs.",
    "provider": "kimi", "model": "model-a",
}


def complete_version(storage, analysis, transcript):
    if not storage.claim_saved_analysis(analysis.job_id, analysis.id):
        raise AnalysisConflictError("Analysis is no longer available")
    analysis.status = AnalysisStatus.COMPLETED
    analysis.summary = f"Summary: {analysis.prompt}"
    analysis.key_points = ["Shared services reduce operating costs."]
    analysis.nodes = copy.deepcopy([NODE])
    if not storage.finish_saved_analysis(analysis, transcript):
        raise AnalysisConflictError("Analysis or transcript changed")
    return storage.get_saved_analysis(analysis.job_id, analysis.id)


def make_storage(directory):
    storage = SQLiteStorage(str(Path(directory) / "test.db"))
    state = StateManager.__new__(StateManager)
    state._storage = storage
    for job_id in (JOB_ID, OTHER_ID):
        job = storage.create_job(f"https://youtube.com/watch?v={job_id}")
        job.stage = Stage.COMPLETED
        storage.update_job(job)
        storage.save_transcript(job_id, Transcript(
            video_url=job.url, title="Infrastructure", transcript_text="Shared infrastructure.",
            words=[Word("Shared", 0, 1000), Word("infrastructure.", 1000, 2000)],
        ))
    return storage, state


class SavedAnalysisRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage, self.state = make_storage(self.directory.name)
        for mock in (
            patch.object(routes, "get_state_manager", return_value=self.state),
            patch("transcripts.config.load_config"),
            patch.dict(os.environ, {
                "KIMI_CODE_API_KEY": "kimi-key", "FIREWORKS_API_KEY": "fireworks-key",
                "FIREWORKS_MODEL": "fireworks-default",
            }, clear=True),
        ):
            mock.start()
            self.addCleanup(mock.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.endpoint = f"/api/jobs/{JOB_ID}/analyses"

    def create(self, **overrides):
        response = self.client.post(self.endpoint, json={**SETTINGS, **overrides})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertIn(response.json()["status"], ("pending", "processing"))
        return response.json()

    def test_reading_uncreated_analyses_never_generates(self):
        with patch.object(routes, "run_saved_analysis") as generate:
            response = self.client.get(self.endpoint)
            detail = self.client.get(f"/api/jobs/{JOB_ID}")
            missing = self.client.get(f"{self.endpoint}/missing")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        self.assertEqual(detail.json()["analyses"], [])
        self.assertEqual(missing.status_code, 404)
        generate.assert_not_called()

    def test_job_detail_has_no_retired_analysis_or_navigation_slots(self):
        with patch.object(routes, "run_saved_analysis") as generate:
            response = self.client.get(f"/api/jobs/{JOB_ID}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"job", "transcript", "analyses"})
        generate.assert_not_called()

    def test_retired_routes_are_unavailable_and_absent_from_openapi(self):
        paths = [
            ("post", f"/api/jobs/{JOB_ID}/analyze"),
            ("get", f"/api/jobs/{JOB_ID}/navigation/timeline"),
            ("get", f"/api/jobs/{JOB_ID}/navigation/topics"),
            ("post", f"/api/jobs/{JOB_ID}/navigation/timeline"),
            ("post", f"/api/jobs/{JOB_ID}/navigation/topics"),
            ("post", f"/api/jobs/{JOB_ID}/navigation/timeline/summaries"),
            ("post", f"/api/jobs/{JOB_ID}/navigation/topics/summaries"),
        ]
        with patch.object(routes, "run_saved_analysis") as generate:
            for method, path in paths:
                with self.subTest(method=method, path=path):
                    response = getattr(self.client, method)(path)
                    self.assertIn(response.status_code, (404, 405))
        generate.assert_not_called()
        self.assertEqual(self.storage.list_saved_analyses(JOB_ID), [])
        schema = self.client.get("/openapi.json").json()
        self.assertNotIn("/api/jobs/{job_id}/analyze", schema["paths"])
        self.assertFalse(any("/navigation/" in path for path in schema["paths"]))
        self.assertNotIn("AnalysisResponse", schema["components"]["schemas"])
        self.assertNotIn("NavigationResponse", schema["components"]["schemas"])

    def test_matching_settings_create_distinct_versions_and_reads_include_both(self):
        with patch.object(routes, "run_saved_analysis", side_effect=complete_version) as generate:
            first = self.create()
            second = self.create()
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(generate.call_count, 2)
        with patch.object(routes, "run_saved_analysis") as generate:
            results = self.client.get(self.endpoint).json()
            current = self.client.get(f"{self.endpoint}/{first['id']}").json()
            detail = self.client.get(f"/api/jobs/{JOB_ID}").json()
        self.assertEqual([item["id"] for item in results], [second["id"], first["id"]])
        self.assertEqual([item["id"] for item in detail["analyses"]], [second["id"], first["id"]])
        self.assertEqual(current["summary"], "Summary: Emphasize costs.")
        self.assertEqual(current["key_points"], ["Shared services reduce operating costs."])
        self.assertEqual(current["nodes"][0]["occurrences"][0]["start"], 0)
        self.assertEqual(current["status"], "completed")
        generate.assert_not_called()

    def test_creation_normalizes_name_and_prompt_and_keeps_selected_settings(self):
        with patch.object(routes, "run_saved_analysis", side_effect=complete_version) as generate:
            result = self.create(name="  Cost focus  ", prompt="  Emphasize costs.  ")
        self.assertEqual(result["name"], "Cost focus")
        self.assertEqual(result["prompt"], "Emphasize costs.")
        analysis = generate.call_args.args[1]
        self.assertEqual((analysis.provider, analysis.model), ("kimi", "model-a"))

    def test_regeneration_always_saves_new_version_and_inherits_settings(self):
        with patch.object(routes, "run_saved_analysis", side_effect=complete_version):
            first = self.create()
            before = self.storage.get_saved_analysis(JOB_ID, first["id"]).to_dict()
            regenerated = self.client.post(f"{self.endpoint}/{first['id']}/regenerate")
            third = self.client.post(f"{self.endpoint}/{first['id']}/regenerate", json={})
        self.assertEqual(regenerated.status_code, 202, regenerated.text)
        self.assertEqual(third.status_code, 202, third.text)
        versions = [first, regenerated.json(), third.json()]
        self.assertEqual(len({item["id"] for item in versions}), 3)
        for item in versions:
            for field in ("name", "view", "prompt", "provider", "model"):
                self.assertEqual(item[field], SETTINGS[field])
        self.assertEqual(self.storage.get_saved_analysis(JOB_ID, first["id"]).to_dict(), before)

    def test_regeneration_accepts_new_settings_without_modifying_parent(self):
        with patch.object(routes, "run_saved_analysis", side_effect=complete_version):
            first = self.create()
            response = self.client.post(f"{self.endpoint}/{first['id']}/regenerate", json={
                "name": "Infrastructure themes", "view": "topics", "prompt": "",
                "provider": "fireworks",
            })
        self.assertEqual(response.status_code, 202, response.text)
        updated = response.json()
        self.assertEqual(updated["name"], "Infrastructure themes")
        self.assertEqual(updated["view"], "topics")
        self.assertEqual(updated["prompt"], "")
        self.assertEqual((updated["provider"], updated["model"]), ("fireworks", "fireworks-default"))
        self.assertEqual(self.storage.get_saved_analysis(JOB_ID, first["id"]).prompt, SETTINGS["prompt"])

    def test_legacy_summary_needs_a_view_before_regeneration(self):
        with patch.object(routes, "run_saved_analysis", side_effect=complete_version):
            first = self.create()
        legacy = self.storage.get_saved_analysis(JOB_ID, first["id"])
        legacy.view = None
        get_analysis = self.storage.get_saved_analysis

        def find_analysis(job_id, analysis_id):
            return legacy if (job_id, analysis_id) == (JOB_ID, legacy.id) else get_analysis(job_id, analysis_id)

        with patch.object(self.storage, "get_saved_analysis", side_effect=find_analysis), \
                patch.object(routes, "run_saved_analysis", side_effect=complete_version) as generate:
            rejected = self.client.post(f"{self.endpoint}/{first['id']}/regenerate")
            self.assertEqual(rejected.status_code, 400)
            generate.assert_not_called()
            created = self.client.post(f"{self.endpoint}/{first['id']}/regenerate", json={"view": "topics"})
            self.assertEqual(created.status_code, 202, created.text)
            self.assertEqual(created.json()["view"], "topics")
            self.assertNotEqual(created.json()["id"], first["id"])

    def test_invalid_settings_and_missing_key_do_not_reserve_or_generate(self):
        invalid = [
            ({"name": "  "}, 400), ({"name": ""}, 422), ({"name": "x" * 201}, 422),
            ({"view": "other"}, 422), ({"provider": "other"}, 422),
            ({"model": "  "}, 400), ({"prompt": "x" * 10001}, 422),
        ]
        with patch.object(routes, "run_saved_analysis") as generate:
            for changes, status in invalid:
                with self.subTest(changes=list(changes)):
                    response = self.client.post(self.endpoint, json={**SETTINGS, **changes})
                    self.assertEqual(response.status_code, status, response.text)
            with patch.dict(os.environ, {}, clear=True):
                response = self.client.post(self.endpoint, json=SETTINGS)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.storage.list_saved_analyses(JOB_ID), [])
        generate.assert_not_called()

    def test_invalid_source_does_not_reserve_or_generate(self):
        with patch.object(routes, "run_saved_analysis") as generate:
            self.assertEqual(self.client.post("/api/jobs/missing/analyses", json=SETTINGS).status_code, 404)
            job = self.state.get_job(JOB_ID)
            job.stage = Stage.PENDING
            self.state.update_job(job)
            self.assertEqual(self.client.post(self.endpoint, json=SETTINGS).status_code, 400)
            job.stage = Stage.COMPLETED
            self.state.update_job(job)
            self.storage.save_transcript(JOB_ID, Transcript(
                video_url=job.url, title="Untimed", transcript_text="Untimed source",
            ))
            response = self.client.post(self.endpoint, json=SETTINGS)
            self.assertEqual(response.status_code, 400)
            self.assertIn("timed passages", response.json()["detail"])
            self.storage.delete_transcript(JOB_ID)
            self.assertEqual(self.client.post(self.endpoint, json=SETTINGS).status_code, 404)
        self.assertEqual(self.storage.list_saved_analyses(JOB_ID), [])
        generate.assert_not_called()

    def test_analysis_ids_are_scoped_to_their_video(self):
        with patch.object(routes, "run_saved_analysis", side_effect=complete_version):
            first = self.create()
        foreign = f"/api/jobs/{OTHER_ID}/analyses/{first['id']}"
        with patch.object(routes, "run_saved_analysis") as generate:
            self.assertEqual(self.client.get(foreign).status_code, 404)
            self.assertEqual(self.client.delete(foreign).status_code, 404)
            self.assertEqual(self.client.post(f"{foreign}/regenerate").status_code, 404)
        self.assertIsNotNone(self.storage.get_saved_analysis(JOB_ID, first["id"]))
        self.assertEqual(self.storage.list_saved_analyses(OTHER_ID), [])
        generate.assert_not_called()

    def test_deleting_one_version_preserves_siblings_and_transcript(self):
        with patch.object(routes, "run_saved_analysis", side_effect=complete_version):
            first = self.create()
            second = self.create(view="topics")
        transcript = self.storage.get_transcript(JOB_ID).to_dict()
        sibling = self.storage.get_saved_analysis(JOB_ID, second["id"]).to_dict()
        response = self.client.delete(f"{self.endpoint}/{first['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True})
        self.assertEqual(self.client.get(f"{self.endpoint}/{first['id']}").status_code, 404)
        self.assertEqual(self.storage.get_saved_analysis(JOB_ID, second["id"]).to_dict(), sibling)
        self.assertEqual(self.storage.get_transcript(JOB_ID).to_dict(), transcript)
        self.assertEqual(self.client.delete(f"{self.endpoint}/{first['id']}").status_code, 404)

    def test_deleting_video_removes_all_versions(self):
        with patch.object(routes, "run_saved_analysis", side_effect=complete_version):
            first = self.create()
            second = self.create(view="topics")
        self.assertEqual(self.client.delete(f"/api/jobs/{JOB_ID}").status_code, 200)
        self.assertIsNone(self.storage.get_saved_analysis(JOB_ID, first["id"]))
        self.assertIsNone(self.storage.get_saved_analysis(JOB_ID, second["id"]))

    def test_generation_failure_is_readable_and_retry_preserves_failed_version(self):
        failure = Analysis(JOB_ID, AnalysisStatus.FAILED, error="Provider unavailable")
        with patch("transcripts.analyses.analyze_transcript", return_value=failure), \
                patch("transcripts.analyses.analyze_navigation") as visualize:
            first = self.create()
        visualize.assert_not_called()
        saved = self.client.get(f"{self.endpoint}/{first['id']}").json()
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["error"], "Provider unavailable")
        with patch.object(routes, "run_saved_analysis", side_effect=complete_version):
            retry = self.client.post(f"{self.endpoint}/{first['id']}/regenerate")
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertNotEqual(retry.json()["id"], first["id"])
        self.assertEqual(self.storage.get_saved_analysis(JOB_ID, first["id"]).status, AnalysisStatus.FAILED)
        self.assertEqual(self.storage.get_saved_analysis(JOB_ID, retry.json()["id"]).status, AnalysisStatus.COMPLETED)

    def test_replaced_transcript_cancels_inflight_version_without_restoring_it(self):
        def replace_source(transcript_text, job_id, **settings):
            self.storage.save_transcript(job_id, Transcript(
                video_url=f"https://youtube.com/watch?v={job_id}", title="Replacement",
                transcript_text="Replacement", words=[Word("Replacement", 3000, 4000)],
            ))
            return Analysis(job_id, AnalysisStatus.COMPLETED, summary="Old source summary")

        with patch("transcripts.analyses.analyze_transcript", side_effect=replace_source), \
                patch("transcripts.analyses.analyze_navigation", return_value=NavigationAnalysis(
                    JOB_ID, "timeline", AnalysisStatus.COMPLETED,
                )):
            first = self.create()
        self.assertEqual(self.client.get(f"{self.endpoint}/{first['id']}").status_code, 404)
        self.assertEqual(self.client.get(self.endpoint).json(), [])


class NonblockingSavedAnalysisTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_stay_responsive_and_deleted_inflight_version_stays_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            storage, state = make_storage(directory)
            entered, release = threading.Event(), threading.Event()

            def slow_analysis(storage, analysis, transcript):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test timed out")
                return complete_version(storage, analysis, transcript)

            with patch.object(routes, "get_state_manager", return_value=state), \
                    patch.object(routes, "run_saved_analysis", side_effect=slow_analysis), \
                    patch("transcripts.config.load_config"), \
                    patch.dict(os.environ, {"KIMI_CODE_API_KEY": "test-key"}, clear=True):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    creation = asyncio.create_task(client.post(f"/api/jobs/{JOB_ID}/analyses", json=SETTINGS))
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                        health = await asyncio.wait_for(client.get("/api/health"), timeout=1)
                        self.assertEqual(health.status_code, 200)
                        results = (await client.get(f"/api/jobs/{JOB_ID}/analyses")).json()
                        self.assertEqual(len(results), 1)
                        deleted = await client.delete(f"/api/jobs/{JOB_ID}/analyses/{results[0]['id']}")
                        self.assertEqual(deleted.status_code, 200)
                    finally:
                        release.set()
                        response = await creation
                    self.assertEqual(response.status_code, 202)
                    self.assertEqual(storage.list_saved_analyses(JOB_ID), [])


if __name__ == "__main__":
    unittest.main()
