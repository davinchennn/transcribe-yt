"""Saved-analysis CLI reads stay read-only and regeneration preserves versions."""

from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
import os
import sqlite3
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from transcripts.cli.main import main
from transcripts.inventory import list_inventory
from transcripts.models import AnalysisStatus, Stage, Transcript, Word
from transcripts.storage.sqlite import SQLiteStorage


class TestAnalysisCLI(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "records.db"
        self.storage = SQLiteStorage(str(self.path))
        self.job = self.storage.create_job("https://youtu.be/abcdefghijk")
        self.job.stage = Stage.COMPLETED
        self.storage.update_job(self.job)
        self.transcript = Transcript(self.job.url, "Video", transcript_text="Source words",
                                     words=[Word("Source", 0, 100), Word("words", 100, 200)])
        self.storage.save_transcript(self.job.id, self.transcript)
        self.transcript = self.storage.get_transcript(self.job.id)

    def save(self, name="Engineering", prompt="Explain tradeoffs", view="timeline"):
        analysis = self.storage.create_saved_analysis(self.job.id, name, view, prompt, "kimi", "k3")
        analysis.summary = "Saved summary"
        analysis.key_points = ["A point"]
        analysis.nodes = [{"id": "chapter", "title": "Chapter", "summary": "Details", "start": 0,
                           "end": 200, "children": [], "occurrences": []}]
        analysis.status = AnalysisStatus.COMPLETED
        self.assertTrue(self.storage.finish_saved_analysis(analysis, self.transcript))
        return analysis

    def cli(self, arguments, writable=False):
        output, error = io.StringIO(), io.StringIO()
        state_patch = (patch("transcripts.cli.main.StateManager", return_value=SimpleNamespace(_storage=self.storage))
                       if writable else patch("transcripts.cli.main.StateManager", side_effect=AssertionError("Read must not initialize storage")))
        with patch.dict(os.environ, {"STORAGE_BACKEND": "sqlite", "STORAGE_PATH": str(self.path)}), \
                patch("sys.argv", ["transcribe"] + arguments), state_patch, \
                redirect_stdout(output), redirect_stderr(error):
            try:
                main()
            except SystemExit as exc:
                return exc.code, output.getvalue(), error.getvalue()
        return 0, output.getvalue(), error.getvalue()

    def test_list_and_read_saved_analyses_without_writes(self):
        first, second = self.save(), self.save("Hiring", "Highlight hiring advice", "topics")
        before = self.path.read_bytes()
        code, output, error = self.cli(["analyses", "--id", self.job.id, "--json"])
        self.assertEqual(code, 0, error)
        analyses = json.loads(output)["analyses"]
        self.assertEqual([item["id"] for item in analyses], [second.id, first.id])
        self.assertEqual(analyses[1]["prompt"], first.prompt)
        self.assertNotIn("nodes", analyses[1])
        code, output, error = self.cli(["analysis", "--id", self.job.id, "--analysis-id", first.id, "--json"])
        self.assertEqual(code, 0, error)
        detail = json.loads(output)["analysis"]
        self.assertEqual(detail["nodes"], first.nodes)
        self.assertEqual(detail["key_points"], first.key_points)
        self.assertEqual(self.path.read_bytes(), before)
        inventory = list_inventory(backend="sqlite", storage_path=str(self.path))
        self.assertEqual(inventory["jobs"][0]["analysis_count"], 2)
        self.assertEqual(inventory["jobs"][0]["analyses"][0]["id"], second.id)

    def test_analysis_read_is_scoped_to_exact_video(self):
        analysis = self.save()
        other = self.storage.create_job("https://youtu.be/lmnopqrstuv")
        code, output, error = self.cli(["analysis", "--id", other.id, "--analysis-id", analysis.id, "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("Analysis not found", error)

    def test_regeneration_inherits_settings_and_saves_a_new_version(self):
        previous = self.save()

        def generate(storage, job_id, name, view, prompt, provider, model):
            self.assertEqual(storage, self.storage)
            self.assertEqual((job_id, name, view, prompt, provider, model),
                             (self.job.id, previous.name, previous.view, "More detail", "kimi", "k3"))
            return self.save(name, prompt, view)

        with patch("transcripts.analyses.create_and_run_analysis", side_effect=generate):
            code, output, error = self.cli(["analyze", "--id", self.job.id, "--from-analysis", previous.id,
                                            "--prompt", "More detail", "--json"], writable=True)
        self.assertEqual(code, 0, error)
        self.assertNotEqual(json.loads(output)["id"], previous.id)
        self.assertEqual(self.storage.get_saved_analysis(self.job.id, previous.id).prompt, previous.prompt)
        self.assertEqual(len(self.storage.list_saved_analyses(self.job.id)), 2)

    def test_prompt_file_and_new_provider_default_are_forwarded(self):
        previous = self.save()
        prompt_file = Path(self.directory.name) / "focus.txt"
        prompt_file.write_text("First instruction\nSecond instruction", encoding="utf-8")
        result = self.save("New version")
        with patch("transcripts.analyses.create_and_run_analysis", return_value=result) as generate:
            code, output, error = self.cli(["analyze", "--id", self.job.id, "--from-analysis", previous.id,
                                            "--provider", "fireworks", "--prompt-file", str(prompt_file)], writable=True)
        self.assertEqual(code, 0, error)
        self.assertEqual(generate.call_args.args[4:], ("First instruction\nSecond instruction", "fireworks", None))

    def test_delete_preserves_sibling_and_transcript(self):
        first, second = self.save(), self.save("Other")
        code, output, error = self.cli(["analysis", "--id", self.job.id, "--analysis-id", first.id, "--delete"], writable=True)
        self.assertEqual(code, 0, error)
        self.assertIsNone(self.storage.get_saved_analysis(self.job.id, first.id))
        self.assertIsNotNone(self.storage.get_saved_analysis(self.job.id, second.id))
        self.assertIsNotNone(self.storage.get_transcript(self.job.id))

    def test_missing_visualization_exits_before_opening_storage(self):
        code, output, error = self.cli(["analyze", "--id", self.job.id])
        self.assertEqual(code, 2)
        self.assertIn("--view is required", error)

    def test_legacy_results_remain_readable_before_migration_with_stable_ids(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE analyses (id INTEGER PRIMARY KEY, job_id TEXT, status TEXT, summary TEXT, key_points TEXT, model TEXT, provider TEXT, error TEXT, created_at TEXT, updated_at TEXT)")
            connection.execute("CREATE TABLE navigation_analyses (id INTEGER PRIMARY KEY, job_id TEXT, view TEXT, status TEXT, summary TEXT, nodes TEXT, model TEXT, provider TEXT, error TEXT, created_at TEXT, updated_at TEXT)")
            connection.execute("INSERT INTO analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (1, self.job.id, "completed", "Legacy summary", "[]", "k3", "kimi", None, "2026-01-01", "2026-01-01"))
            connection.execute("INSERT INTO navigation_analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (1, self.job.id, "topics", "completed", "Legacy topics", "[]", "k3", "kimi", None, "2026-01-02", "2026-01-02"))
            connection.execute("DROP TABLE video_analyses")
            connection.execute("DROP TABLE schema_migrations")
        before = self.path.read_bytes()
        code, output, error = self.cli(["analyses", "--id", self.job.id, "--json"])
        self.assertEqual(code, 0, error)
        legacy = json.loads(output)["analyses"]
        self.assertEqual(len(legacy), 2)
        code, output, error = self.cli(["analysis", "--id", self.job.id, "--analysis-id", legacy[0]["id"], "--json"])
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["analysis"]["summary"], "Legacy topics")
        self.assertEqual(self.path.read_bytes(), before)
        migrated = SQLiteStorage(str(self.path)).list_saved_analyses(self.job.id)
        self.assertEqual([item["id"] for item in legacy], [item.id for item in migrated])

    def test_failed_generation_keeps_json_result_and_exits_one(self):
        analysis = self.storage.create_saved_analysis(self.job.id, "Failed analysis", "timeline", "", "kimi", "k3")
        analysis.status = AnalysisStatus.FAILED
        analysis.error = "Provider unavailable"
        self.assertTrue(self.storage.finish_saved_analysis(analysis, self.transcript))
        with patch("transcripts.analyses.create_and_run_analysis", return_value=analysis):
            code, output, error = self.cli(["analyze", "--id", self.job.id, "--view", "timeline", "--json"], writable=True)
        self.assertEqual(code, 1)
        self.assertEqual(error, "")
        self.assertEqual(json.loads(output)["error"], "Provider unavailable")


if __name__ == "__main__":
    unittest.main()
