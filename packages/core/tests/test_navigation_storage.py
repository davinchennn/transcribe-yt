"""Independent navigation caches and atomic creation reservations."""

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

from transcripts.models import AnalysisStatus, NavigationAnalysis, Stage, Transcript, Word
from transcripts.storage.sqlite import SQLiteStorage


class TestNavigationStorage(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = SQLiteStorage(str(Path(self.directory.name) / "test.db"))
        self.job = self.storage.create_job("https://youtu.be/abcdefghijk")

    def test_views_are_cached_independently_and_round_trip(self):
        nodes = [{"id": "n1", "title": "Cost", "summary": "Cost discussion", "start": 1200,
                  "end": 2400, "children": [], "occurrences": [{"id": "p1", "start": 1200,
                  "end": 2400, "text": "Source text", "utterance_start": 0, "utterance_end": 0}]}]
        timeline = NavigationAnalysis(self.job.id, "timeline", AnalysisStatus.COMPLETED,
                                      summary="Overview", nodes=nodes, model="k3")
        self.storage.save_navigation(timeline)
        self.assertEqual(self.storage.get_navigation(self.job.id, "timeline").to_dict(), timeline.to_dict())
        self.assertIsNone(self.storage.get_navigation(self.job.id, "topics"))
        topics = NavigationAnalysis(self.job.id, "topics", AnalysisStatus.FAILED, error="Try again")
        self.storage.save_navigation(topics)
        self.assertEqual(self.storage.get_navigation(self.job.id, "topics").error, "Try again")
        self.assertEqual(self.storage.get_navigation(self.job.id, "timeline").nodes, nodes)
        self.assertTrue(self.storage.delete_navigation(self.job.id))
        self.assertIsNone(self.storage.get_navigation(self.job.id, "timeline"))
        self.assertIsNone(self.storage.get_navigation(self.job.id, "topics"))

    def test_only_one_concurrent_request_claims_a_view(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            claims = list(executor.map(lambda _: self.storage.claim_navigation(self.job.id, "timeline"), range(8)))
        self.assertEqual(sum(claims), 1)
        self.assertTrue(self.storage.claim_navigation(self.job.id, "topics"))
        self.assertEqual(self.storage.get_navigation(self.job.id, "timeline").status, AnalysisStatus.PROCESSING)
        self.assertFalse(self.storage.claim_navigation(self.job.id, "timeline"))

    def test_failed_retries_but_completed_results_are_not_claimed(self):
        self.storage.save_navigation(NavigationAnalysis(self.job.id, "timeline", AnalysisStatus.FAILED, error="Network"))
        created_at = self.storage.get_navigation(self.job.id, "timeline").created_at
        self.assertTrue(self.storage.claim_navigation(self.job.id, "timeline"))
        retried = self.storage.get_navigation(self.job.id, "timeline")
        self.assertIsNone(retried.error)
        self.assertEqual(retried.created_at, created_at)
        self.storage.save_navigation(NavigationAnalysis(self.job.id, "timeline", AnalysisStatus.COMPLETED))
        self.assertFalse(self.storage.claim_navigation(self.job.id, "timeline"))

    def test_reserved_creation_time_is_preserved_on_save(self):
        self.storage.claim_navigation(self.job.id, "timeline")
        reserved_at = self.storage.get_navigation(self.job.id, "timeline").created_at
        result = NavigationAnalysis(self.job.id, "timeline", AnalysisStatus.COMPLETED)
        self.storage.save_navigation(result)
        self.assertEqual(result.created_at, reserved_at)
        self.assertEqual(self.storage.get_navigation(self.job.id, "timeline").to_dict(), result.to_dict())

    def test_deleted_job_cannot_acquire_new_reservation(self):
        self.storage.delete_job(self.job.id)
        self.assertFalse(self.storage.claim_navigation(self.job.id, "timeline"))
        self.assertIsNone(self.storage.get_navigation(self.job.id, "timeline"))

    def test_stale_processing_is_recovered_and_live_lease_is_respected(self):
        self.assertTrue(self.storage.claim_navigation(self.job.id, "timeline"))
        stale = (datetime.utcnow() - timedelta(minutes=20)).isoformat()
        with self.storage._get_connection() as connection:
            connection.execute("UPDATE navigation_analyses SET updated_at = ?", (stale,))
        self.assertTrue(self.storage.claim_navigation(self.job.id, "timeline"))
        self.assertFalse(self.storage.claim_navigation(self.job.id, "timeline"))
        self.assertTrue(self.storage.lease_navigation(self.job.id, "timeline"))
        self.storage.delete_navigation(self.job.id)
        self.assertFalse(self.storage.lease_navigation(self.job.id, "timeline"))
        self.assertIsNone(self.storage.get_navigation(self.job.id, "timeline"))

    def test_delete_job_cleans_navigation_rows_without_foreign_keys(self):
        self.storage.claim_navigation(self.job.id, "timeline")
        self.storage.claim_navigation(self.job.id, "topics")
        self.assertTrue(self.storage.delete_job(self.job.id))
        self.assertIsNone(self.storage.get_navigation(self.job.id, "timeline"))
        self.assertIsNone(self.storage.get_navigation(self.job.id, "topics"))

    def test_filtered_and_unfiltered_clear_cleanup_only_deleted_job_caches(self):
        other = self.storage.create_job("https://youtu.be/lmnopqrstuv")
        self.storage.set_stage(self.job.id, Stage.COMPLETED)
        self.storage.claim_navigation(self.job.id, "timeline")
        self.storage.claim_navigation(other.id, "topics")
        self.assertEqual(self.storage.clear_jobs(Stage.COMPLETED), 1)
        self.assertIsNone(self.storage.get_navigation(self.job.id, "timeline"))
        self.assertIsNotNone(self.storage.get_navigation(other.id, "topics"))
        self.assertEqual(self.storage.clear_jobs(), 1)
        self.assertIsNone(self.storage.get_navigation(other.id, "topics"))

    def test_invalid_view_is_rejected(self):
        with self.assertRaises(ValueError):
            self.storage.claim_navigation(self.job.id, "unknown")
        with self.assertRaises(ValueError):
            self.storage.save_navigation(NavigationAnalysis(self.job.id, "unknown"))

    def test_identical_transcript_save_preserves_both_navigation_caches(self):
        transcript = Transcript(self.job.url, "Title", transcript_text="Original words",
                                words=[Word("Original", 1200, 1500), Word("words", 1600, 1900)])
        self.storage.save_transcript(self.job.id, transcript)
        self.storage.save_navigation(NavigationAnalysis(self.job.id, "timeline", AnalysisStatus.COMPLETED))
        self.storage.save_navigation(NavigationAnalysis(self.job.id, "topics", AnalysisStatus.COMPLETED))
        transcript.title = "Updated title"
        self.storage.save_transcript(self.job.id, transcript)
        self.assertIsNotNone(self.storage.get_navigation(self.job.id, "timeline"))
        self.assertIsNotNone(self.storage.get_navigation(self.job.id, "topics"))

    def test_changed_transcript_text_or_word_timing_invalidates_both_caches(self):
        for change in ("text", "timing", "word_text"):
            with self.subTest(change=change):
                transcript = Transcript(self.job.url, "Title", transcript_text="Original words",
                                        words=[Word("Original", 1200, 1500), Word("words", 1600, 1900)])
                self.storage.save_transcript(self.job.id, transcript)
                self.storage.save_navigation(NavigationAnalysis(self.job.id, "timeline", AnalysisStatus.COMPLETED))
                self.storage.save_navigation(NavigationAnalysis(self.job.id, "topics", AnalysisStatus.COMPLETED))
                if change == "text":
                    transcript.transcript_text = "Replacement text"
                elif change == "timing":
                    transcript.words[0].start = 1100
                else:
                    transcript.words[0].text = "Changed"
                self.storage.save_transcript(self.job.id, transcript)
                self.assertIsNone(self.storage.get_navigation(self.job.id, "timeline"))
                self.assertIsNone(self.storage.get_navigation(self.job.id, "topics"))
                self.assertEqual(self.storage.get_transcript(self.job.id).transcript_text, transcript.transcript_text)

    def summary_snapshot(self):
        self.storage.save_transcript(self.job.id, Transcript(
            self.job.url, "Title", transcript_text="Original words",
            words=[Word("Original", 1200, 1500), Word("words", 1600, 1900)],
        ))
        occurrence = {"id": "p1", "start": 1200, "end": 1900, "text": "Original words",
                      "utterance_start": 0, "utterance_end": 0, "word_start": 0, "word_end": 1}
        child = {"id": "child", "title": "Words", "summary": "Old child summary", "start": 1200,
                 "end": 1900, "occurrences": [deepcopy(occurrence)], "children": []}
        root = {"id": "root", "title": "Original", "summary": "Keep root summary", "start": 1200,
                "end": 1900, "occurrences": [occurrence], "children": [child]}
        self.storage.save_navigation(NavigationAnalysis(
            self.job.id, "timeline", AnalysisStatus.COMPLETED,
            summary="Keep overview", nodes=[root], model="original-model",
        ))
        expected = self.storage.get_navigation(self.job.id, "timeline")
        updated = deepcopy(expected)
        updated.nodes[0]["children"][0]["summary"] = "Updated child summary"
        return expected, updated, self.storage.get_transcript(self.job.id)

    def test_conditional_summary_save_preserves_original_fields_and_other_view(self):
        expected, updated, transcript = self.summary_snapshot()
        self.storage.save_navigation(NavigationAnalysis(
            self.job.id, "topics", AnalysisStatus.COMPLETED, summary="Other view",
        ))
        topics = self.storage.get_navigation(self.job.id, "topics").to_dict()
        self.assertTrue(self.storage.save_navigation_if_current(updated, expected, transcript))
        stored = self.storage.get_navigation(self.job.id, "timeline")
        self.assertEqual(stored.to_dict(), updated.to_dict())
        self.assertNotEqual(stored.updated_at, expected.updated_at)
        self.assertEqual(stored.created_at, expected.created_at)
        old_fields = expected.to_dict()
        new_fields = stored.to_dict()
        for key in old_fields:
            if key not in ("nodes", "updated_at"):
                self.assertEqual(new_fields[key], old_fields[key])
        self.assertEqual(stored.nodes[0]["summary"], "Keep root summary")
        self.assertEqual(self.storage.get_navigation(self.job.id, "topics").to_dict(), topics)

    def test_concurrent_conditional_summary_updates_allow_only_one_snapshot_to_save(self):
        expected, updated, transcript = self.summary_snapshot()

        def save(index):
            candidate = deepcopy(updated)
            candidate.nodes[0]["children"][0]["summary"] = f"Candidate {index}"
            return self.storage.save_navigation_if_current(candidate, expected, transcript)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(save, range(8)))
        self.assertEqual(sum(results), 1)
        self.assertTrue(self.storage.get_navigation(self.job.id, "timeline").nodes[0]["children"][0]["summary"].startswith("Candidate "))

    def test_conditional_summary_save_rejects_every_changed_navigation_version_field(self):
        changes = {"status": "failed", "summary": "Changed overview", "nodes": "[]",
                   "model": "new-model", "error": "Changed error", "created_at": "changed",
                   "updated_at": "changed"}
        for field, value in changes.items():
            with self.subTest(field=field):
                expected, updated, transcript = self.summary_snapshot()
                original_candidate = deepcopy(updated.to_dict())
                with self.storage._get_connection() as connection:
                    connection.execute(f"UPDATE navigation_analyses SET {field} = ? WHERE job_id = ? AND view = ?",
                                       (value, self.job.id, "timeline"))
                changed = self.storage.get_navigation(self.job.id, "timeline").to_dict()
                self.assertFalse(self.storage.save_navigation_if_current(updated, expected, transcript))
                self.assertEqual(self.storage.get_navigation(self.job.id, "timeline").to_dict(), changed)
                self.assertEqual(updated.to_dict(), original_candidate)

    def test_conditional_summary_save_rejects_changed_source_even_when_cache_survives(self):
        for change in ("text", "word_text", "word_timing", "word_speaker"):
            with self.subTest(change=change):
                expected, updated, transcript = self.summary_snapshot()
                with self.storage._get_connection() as connection:
                    if change == "text":
                        connection.execute("UPDATE transcripts SET transcript_text = ? WHERE job_id = ?",
                                           ("Changed source", self.job.id))
                    else:
                        words = json.loads(connection.execute("SELECT words FROM transcripts WHERE job_id = ?",
                                                              (self.job.id,)).fetchone()["words"])
                        if change == "word_text":
                            words[0]["text"] = "Changed"
                        elif change == "word_timing":
                            words[0]["start"] = 1100
                        else:
                            words[0]["speaker"] = "Different"
                        connection.execute("UPDATE transcripts SET words = ? WHERE job_id = ?",
                                           (json.dumps(words), self.job.id))
                self.assertFalse(self.storage.save_navigation_if_current(updated, expected, transcript))
                self.assertEqual(self.storage.get_navigation(self.job.id, "timeline").to_dict(), expected.to_dict())

    def test_conditional_summary_save_compares_effective_utterances_in_source_snapshot(self):
        expected, updated, transcript = self.summary_snapshot()
        transcript.utterances[0].text = "Stale utterance"
        self.assertFalse(self.storage.save_navigation_if_current(updated, expected, transcript))
        self.assertEqual(self.storage.get_navigation(self.job.id, "timeline").to_dict(), expected.to_dict())

    def test_conditional_summary_save_never_recreates_deleted_navigation_or_source(self):
        for missing in ("navigation", "transcript"):
            with self.subTest(missing=missing):
                expected, updated, transcript = self.summary_snapshot()
                if missing == "navigation":
                    self.storage.delete_navigation(self.job.id)
                else:
                    self.storage.delete_transcript(self.job.id)
                self.assertFalse(self.storage.save_navigation_if_current(updated, expected, transcript))
                if missing == "navigation":
                    self.assertIsNone(self.storage.get_navigation(self.job.id, "timeline"))
                else:
                    self.assertIsNone(self.storage.get_transcript(self.job.id))
                    self.assertEqual(self.storage.get_navigation(self.job.id, "timeline").to_dict(), expected.to_dict())

    def test_conditional_summary_save_rejects_root_hierarchy_or_metadata_changes(self):
        for change in ("root_summary", "title", "occurrence", "hierarchy", "status", "created_at"):
            with self.subTest(change=change):
                expected, updated, transcript = self.summary_snapshot()
                if change == "root_summary":
                    updated.nodes[0]["summary"] = "Changed root"
                elif change == "title":
                    updated.nodes[0]["children"][0]["title"] = "Changed title"
                elif change == "occurrence":
                    updated.nodes[0]["children"][0]["occurrences"][0]["start"] = 999
                elif change == "hierarchy":
                    updated.nodes[0]["children"].append(deepcopy(updated.nodes[0]["children"][0]))
                elif change == "status":
                    updated.status = AnalysisStatus.FAILED
                else:
                    updated.created_at = "Changed timestamp"
                with self.assertRaisesRegex(ValueError, "preserve"):
                    self.storage.save_navigation_if_current(updated, expected, transcript)
                self.assertEqual(self.storage.get_navigation(self.job.id, "timeline").to_dict(), expected.to_dict())


if __name__ == "__main__":
    unittest.main()
