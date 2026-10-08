"""Saved analysis history, migration, generation claims, and focus propagation."""

import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from transcripts.analyses import AnalysisConflictError, create_and_run_analysis, run_saved_analysis
from transcripts.analyzer import analyze_transcript
from transcripts.models import Analysis, AnalysisStatus, NavigationAnalysis, Stage, Transcript, Utterance, Word
from transcripts.navigation import analyze_navigation
from transcripts.storage.json import JSONStorage
from transcripts.storage.sqlite import SQLiteStorage


class SavedAnalysisTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "records.db"
        self.storage = SQLiteStorage(str(self.path))
        self.job = self.storage.create_job("https://youtu.be/abcdefghijk")
        self.storage.set_stage(self.job.id, Stage.COMPLETED)
        self.storage.save_transcript(self.job.id, Transcript(
            video_url=self.job.url, title="Video", transcript_text="First Second",
            words=[Word("First", 0, 100), Word("Second", 2500, 2600)],
        ))
        self.transcript = self.storage.get_transcript(self.job.id)
        self.config = patch("transcripts.config.load_config")
        self.config.start()
        self.addCleanup(self.config.stop)
        self.environment = patch.dict(os.environ, {"KIMI_CODE_API_KEY": "test-key", "ANALYSIS_PROVIDER": "kimi", "KIMI_MODEL": "k3"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def create(self, name="Costs", view="timeline", prompt="Focus on costs"):
        return self.storage.create_saved_analysis(self.job.id, name, view, prompt, "kimi", "k3")

    def results(self):
        return (
            Analysis(self.job.id, AnalysisStatus.COMPLETED, summary="A summary", key_points=["A point"]),
            NavigationAnalysis(self.job.id, "timeline", AnalysisStatus.COMPLETED, nodes=[{"id": "timeline-1"}]),
        )

    def test_versions_are_independent_newest_first_and_scoped_to_job(self):
        first, second = self.create(), self.create()
        self.assertNotEqual(first.id, second.id)
        self.assertEqual([row.id for row in self.storage.list_saved_analyses(self.job.id)], [second.id, first.id])
        self.assertIsNone(self.storage.get_saved_analysis("different-job", first.id))
        self.assertFalse(self.storage.delete_saved_analysis("different-job", first.id))
        self.assertTrue(self.storage.delete_saved_analysis(self.job.id, first.id))
        self.assertEqual([row.id for row in self.storage.list_saved_analyses(self.job.id)], [second.id])

    def test_one_worker_claims_and_completion_is_immutable(self):
        analysis = self.create()
        with ThreadPoolExecutor(max_workers=8) as workers:
            claims = list(workers.map(lambda _: self.storage.claim_saved_analysis(self.job.id, analysis.id), range(8)))
        self.assertEqual(claims.count(True), 1)
        analysis.status, analysis.summary = AnalysisStatus.COMPLETED, "Original result"
        self.assertTrue(self.storage.finish_saved_analysis(analysis, self.transcript))
        analysis.summary = "Replacement"
        self.assertFalse(self.storage.finish_saved_analysis(analysis, self.transcript))
        self.assertEqual(self.storage.get_saved_analysis(self.job.id, analysis.id).summary, "Original result")

    def test_deleted_or_changed_source_never_recreates_versions(self):
        analysis = self.create()
        analysis.status = AnalysisStatus.COMPLETED
        self.storage.delete_saved_analysis(self.job.id, analysis.id)
        self.assertFalse(self.storage.finish_saved_analysis(analysis, self.transcript))
        analysis = self.create()
        analysis.status = AnalysisStatus.COMPLETED
        changed = deepcopy(self.transcript)
        changed.words[0].end += 10
        self.assertFalse(self.storage.finish_saved_analysis(analysis, changed))
        self.storage.save_transcript(self.job.id, changed)
        self.assertEqual(self.storage.list_saved_analyses(self.job.id), [])
        self.assertFalse(self.storage.finish_saved_analysis(analysis, self.transcript))

    def test_metadata_only_source_save_preserves_versions(self):
        analysis = self.create()
        updated = deepcopy(self.transcript)
        updated.metadata["description"] = "Updated description"
        self.storage.save_transcript(self.job.id, updated)
        analysis.status = AnalysisStatus.COMPLETED
        self.assertTrue(self.storage.finish_saved_analysis(analysis, self.transcript))

    def test_job_delete_and_clear_cleanup_versions(self):
        self.create()
        second = self.storage.create_job("https://youtu.be/12345678901")
        self.storage.set_stage(second.id, Stage.COMPLETED)
        self.storage.save_transcript(second.id, self.transcript)
        other = self.storage.create_saved_analysis(second.id, "Other", "topics")
        self.storage.delete_job(self.job.id)
        self.assertEqual(self.storage.list_saved_analyses(self.job.id), [])
        self.assertIsNotNone(self.storage.get_saved_analysis(second.id, other.id))
        self.storage.clear_jobs(Stage.COMPLETED)
        self.assertEqual(self.storage.list_saved_analyses(second.id), [])

    def test_legacy_results_migrate_once_without_losing_metadata(self):
        summary = Analysis(self.job.id, AnalysisStatus.COMPLETED, summary="Saved summary", key_points=["Saved point"],
                           provider="fireworks", model="summary-model", created_at="2020-01-01T00:00:00")
        timeline = NavigationAnalysis(self.job.id, "timeline", AnalysisStatus.COMPLETED, summary="Timeline summary",
                                      nodes=[{"id": "timeline-1"}], provider="kimi", model="timeline-model")
        topics = NavigationAnalysis(self.job.id, "topics", AnalysisStatus.FAILED, error="Saved failure", provider="fireworks")
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE video_analyses")
            conn.execute("DROP TABLE schema_migrations")
            conn.execute("CREATE TABLE analyses (id INTEGER PRIMARY KEY, job_id TEXT, status TEXT, summary TEXT, key_points TEXT, provider TEXT, model TEXT, error TEXT, created_at TEXT, updated_at TEXT)")
            conn.execute("CREATE TABLE navigation_analyses (id INTEGER PRIMARY KEY, job_id TEXT, view TEXT, status TEXT, summary TEXT, nodes TEXT, provider TEXT, model TEXT, error TEXT, created_at TEXT, updated_at TEXT)")
            conn.execute("INSERT INTO analyses VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (summary.job_id, summary.status.value, summary.summary, '["Saved point"]', summary.provider,
                          summary.model, summary.error, summary.created_at, summary.updated_at))
            for index, navigation in enumerate((timeline, topics), 1):
                conn.execute("INSERT INTO navigation_analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (index, navigation.job_id, navigation.view, navigation.status.value, navigation.summary,
                              '[{"id": "timeline-1"}]' if navigation.view == "timeline" else "[]", navigation.provider,
                              navigation.model, navigation.error, navigation.created_at, navigation.updated_at))
        with patch("transcripts.llm.request_json") as requests:
            self.storage = SQLiteStorage(str(self.path))
        requests.assert_not_called()
        records = {result.view: result for result in self.storage.list_saved_analyses(self.job.id)}
        self.assertEqual(len(records), 3)
        self.assertEqual(records[None].name, "General summary")
        self.assertEqual(records[None].key_points, summary.key_points)
        self.assertEqual(records[None].provider, "fireworks")
        self.assertEqual(records[None].created_at, summary.created_at)
        self.assertEqual(records["timeline"].summary, timeline.summary)
        self.assertEqual(records["timeline"].nodes, timeline.nodes)
        self.assertEqual(records["topics"].error, "Saved failure")
        with sqlite3.connect(self.path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertNotIn("analyses", tables)
        self.assertNotIn("navigation_analyses", tables)
        self.storage.delete_saved_analysis(self.job.id, records[None].id)
        self.storage = SQLiteStorage(str(self.path))
        self.assertEqual(len(self.storage.list_saved_analyses(self.job.id)), 2)

    def test_service_generates_all_outputs_and_passes_saved_focus(self):
        summary, navigation = self.results()
        with patch("transcripts.analyses.analyze_transcript", return_value=summary) as summarize, \
                patch("transcripts.analyses.analyze_navigation", return_value=navigation) as navigate:
            result = create_and_run_analysis(self.storage, self.job.id, " Costs ", "timeline", " Focus on costs ")
        self.assertEqual(result.status, AnalysisStatus.COMPLETED)
        self.assertEqual(result.name, "Costs")
        self.assertEqual(result.summary, "A summary")
        self.assertEqual(result.key_points, ["A point"])
        self.assertEqual(result.nodes, navigation.nodes)
        self.assertEqual(summarize.call_args.kwargs["prompt"], "Focus on costs")
        self.assertEqual(navigate.call_args.kwargs["prompt"], "Focus on costs")
        with patch("transcripts.analyses.analyze_transcript") as summarize:
            with self.assertRaises(AnalysisConflictError):
                run_saved_analysis(self.storage, result, self.transcript)
            summarize.assert_not_called()

    def test_failed_visualization_retains_summary_and_delete_during_run_conflicts(self):
        summary, navigation = self.results()
        navigation.status, navigation.error = AnalysisStatus.FAILED, "Invalid ranges"
        with patch("transcripts.analyses.analyze_transcript", return_value=summary), \
                patch("transcripts.analyses.analyze_navigation", return_value=navigation):
            failed = create_and_run_analysis(self.storage, self.job.id, "Failure", "timeline")
        self.assertEqual(failed.status, AnalysisStatus.FAILED)
        self.assertEqual(failed.summary, summary.summary)
        self.assertEqual(failed.error, "Invalid ranges")
        pending = self.create()
        def delete_while_running(*args, **kwargs):
            self.storage.delete_saved_analysis(self.job.id, pending.id)
            return summary
        with patch("transcripts.analyses.analyze_transcript", side_effect=delete_while_running), \
                patch("transcripts.analyses.analyze_navigation", return_value=self.results()[1]):
            with self.assertRaises(AnalysisConflictError):
                run_saved_analysis(self.storage, pending, self.transcript)
        self.assertIsNone(self.storage.get_saved_analysis(self.job.id, pending.id))

    def test_source_changed_before_reservation_fails_without_inference(self):
        original = self.transcript
        replacement = deepcopy(original)
        replacement.transcript_text = "Different transcription"
        self.storage.save_transcript(self.job.id, replacement)
        analysis = self.create()
        with patch("transcripts.analyses.analyze_transcript") as summarize, \
                patch("transcripts.analyses.analyze_navigation") as navigate:
            with self.assertRaises(AnalysisConflictError):
                run_saved_analysis(self.storage, analysis, original)
        summarize.assert_not_called()
        navigate.assert_not_called()
        result = self.storage.get_saved_analysis(self.job.id, analysis.id)
        self.assertEqual(result.status, AnalysisStatus.FAILED)
        self.assertIn("Transcript changed before analysis started", result.error)

    def test_validation_creates_no_record_and_sends_no_requests(self):
        invalids = [("", "timeline", ""), ("A" * 201, "timeline", ""), ("Name", "other", ""),
                    ("Name", "topics", "A" * 10001)]
        with patch("transcripts.analyses.analyze_transcript") as summarize:
            for name, view, prompt in invalids:
                with self.subTest(name=name[:10], view=view), self.assertRaises(ValueError):
                    create_and_run_analysis(self.storage, self.job.id, name, view, prompt)
            with patch("transcripts.analyses.inference_api_key", side_effect=ValueError("Missing key")), self.assertRaises(ValueError):
                create_and_run_analysis(self.storage, self.job.id, "Name", "topics")
            untimed = deepcopy(self.transcript)
            untimed.words, untimed.utterances = [], []
            self.storage.save_transcript(self.job.id, untimed)
            with self.assertRaises(ValueError):
                create_and_run_analysis(self.storage, self.job.id, "Name", "topics")
            summarize.assert_not_called()
        self.assertEqual(self.storage.list_saved_analyses(self.job.id), [])
        with self.assertRaisesRegex(ValueError, "does not support"):
            create_and_run_analysis(JSONStorage(str(self.path.with_suffix(".json"))), self.job.id, "Name", "topics")


class FocusPropagationTests(unittest.TestCase):
    def test_summary_focus_supplements_required_json_format(self):
        with patch("transcripts.analyzer.request_json", return_value={"summary": "Summary", "key_points": ["Point"]}) as request:
            result = analyze_transcript("Transcript", "job", prompt="Emphasize deployment decisions")
        self.assertEqual(result.status, AnalysisStatus.COMPLETED)
        system = request.call_args.args[0]
        self.assertIn("Emphasize deployment decisions", system)
        self.assertIn('"key_points"', system)
        self.assertIn("coverage rules above remain mandatory", system)
        self.assertEqual(request.call_args.args[1], "Transcript")

    def transcript(self):
        return Transcript(video_url="", title="Video", utterances=[
            Utterance("A", f"Passage {index}", index * 2000, index * 2000 + 1000) for index in range(4)
        ])

    def chapter(self, title, first, last):
        return {"title": title, "summary": "Concrete factual summary", "start_segment": first, "end_segment": last, "children": []}

    def test_focus_reaches_chunk_regroup_and_subtopic_repair_calls(self):
        responses = [
            {"nodes": [{**self.chapter("First", 0, 1), "summary": ""}]},
            {"nodes": [self.chapter("Second", 2, 3)]},
            {"nodes": [self.chapter("Whole", 0, 1)]},
            {"summaries": [{"node_id": "timeline-2", "summary": " ".join(["Long"] * 21)}]},
            {"summaries": [{"node_id": "timeline-2", "summary": "Repaired factual focus"}]},
        ]
        with patch("transcripts.navigation.MAX_CHUNK_SEGMENTS", 2), \
                patch("transcripts.navigation.request_json", side_effect=responses) as request:
            result = analyze_navigation(self.transcript(), "job", "timeline", prompt="Focus on infrastructure costs")
        self.assertEqual(result.status, AnalysisStatus.COMPLETED, result.error)
        self.assertEqual(request.call_count, 5)
        for call in request.call_args_list:
            self.assertIn("Focus on infrastructure costs", call.args[0])
            self.assertIn("must still cover the entire source", call.args[0])
        self.assertEqual(result.nodes[0]["occurrences"][0]["utterance_end"], 3)

    def test_focus_reaches_recurring_topic_regroup(self):
        responses = [
            {"nodes": [{"title": "Cost", "summary": "First costs", "ranges": [[0, 1]], "children": []}]},
            {"nodes": [{"title": "Costs", "summary": "Second costs", "ranges": [[2, 3]], "children": []}]},
            {"nodes": [{"title": "Cost", "summary": "Recurring costs", "source_ids": [0, 1], "children": []}]},
        ]
        with patch("transcripts.navigation.MAX_CHUNK_SEGMENTS", 2), \
                patch("transcripts.navigation.request_json", side_effect=responses) as request:
            result = analyze_navigation(self.transcript(), "job", "topics", prompt="Prioritize costs")
        self.assertEqual(result.status, AnalysisStatus.COMPLETED, result.error)
        self.assertEqual(request.call_count, 3)
        self.assertTrue(all("Prioritize costs" in call.args[0] for call in request.call_args_list))


if __name__ == "__main__":
    unittest.main()
