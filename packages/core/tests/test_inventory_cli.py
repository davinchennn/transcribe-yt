"""CLI discovery distinguishes sources and reads existing data without bootstrap."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from transcripts.cli.main import main
from transcripts.inventory import list_inventory
from transcripts.models import Analysis, AnalysisStatus, NavigationAnalysis, Stage, Transcript, Word
from transcripts.storage.sqlite import SQLiteStorage


class TestInventoryCLI(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "records.db"
        self.storage = SQLiteStorage(str(self.path))
        self.youtube = self.storage.create_job("https://youtu.be/abcdefghijk")
        self.x = self.storage.create_job("https://x.com/lauren/status/12345")
        self.title = "Lauren talks about coding agents with a deliberately long complete title"
        for job in (self.youtube, self.x):
            job.title = self.title
            job.stage = Stage.COMPLETED
            job.provider = "deepgram"
            self.storage.update_job(job)
        self.video = self.root / "saved.mp4"
        self.video.write_bytes(b"fixture")
        self.x.video_file = str(self.video)
        self.x.audio_file = str(self.root / "removed.mp3")
        self.storage.update_job(self.x)
        self.storage.save_transcript(self.x.id, Transcript(
            self.x.url, self.title, duration=12.345, transcript_text="Source words",
            words=[Word("Source", 1000, 1200), Word("words", 1300, 1500)],
        ))
        nodes = [{"id": "root", "children": [{"id": "child", "children": [], "occurrences": [{}]}], "occurrences": [{}]}]
        self.storage.save_navigation(NavigationAnalysis(self.x.id, "topics", AnalysisStatus.COMPLETED, nodes=nodes, model="k3"))
        self.storage.save_navigation(NavigationAnalysis(self.youtube.id, "topics", AnalysisStatus.FAILED, error="Invalid ranges"))
        self.storage.save_analysis(Analysis(self.youtube.id, AnalysisStatus.COMPLETED, key_points=["Point"], model="k3"))

    def inventory(self, **filters):
        return list_inventory(backend="sqlite", storage_path=str(self.path), **filters)

    def cli(self, arguments, storage_path=None, backend="sqlite"):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, {"STORAGE_PATH": str(storage_path or self.path), "STORAGE_BACKEND": backend}), \
                patch("sys.argv", ["transcribe"] + arguments), \
                patch("transcripts.cli.main.StateManager", side_effect=AssertionError("Storage must not initialize")), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                main()
            except SystemExit as error:
                return error.code, stdout.getvalue(), stderr.getvalue()
        return 0, stdout.getvalue(), stderr.getvalue()

    def test_duplicate_titles_keep_distinct_source_identity_and_saved_analysis_states(self):
        inventory = self.inventory(query="LAUREN")
        self.assertEqual(inventory["total"], 2)
        self.assertEqual(inventory["storage"], {"backend": "sqlite", "path": str(self.path.resolve())})
        jobs = {job["id"]: job for job in inventory["jobs"]}
        x = jobs[self.x.id]
        self.assertEqual(x["source"], "x")
        self.assertEqual(x["transcription_provider"], "deepgram")
        self.assertEqual(x["transcript"], {
            "available": True, "storage": "database", "duration_seconds": 12.345,
            "word_count": 2, "timings_available": True,
        })
        self.assertTrue(x["files"]["video"]["exists"])
        self.assertFalse(x["files"]["audio"]["exists"])
        self.assertFalse(x["files"]["transcript_export"]["exists"])
        self.assertEqual(x["analysis"]["status"], "not_created")
        self.assertEqual(x["navigation"]["topics"]["status"], "completed")
        self.assertEqual(x["navigation"]["topics"]["node_count"], 2)
        self.assertEqual(x["navigation"]["topics"]["depth"], 2)
        self.assertEqual(x["navigation"]["topics"]["occurrence_count"], 2)
        self.assertEqual(x["navigation"]["timeline"]["status"], "not_created")
        youtube = jobs[self.youtube.id]
        self.assertEqual(youtube["source"], "youtube")
        self.assertFalse(youtube["transcript"]["available"])
        self.assertEqual(youtube["analysis"]["key_point_count"], 1)
        self.assertEqual(youtube["navigation"]["topics"]["status"], "failed")
        self.assertEqual(youtube["navigation"]["topics"]["error"], "Invalid ranges")

    def test_filters_combine_and_match_titles_urls_and_exact_ids(self):
        for query in ("lauren", "x.com", self.x.id):
            with self.subTest(query=query):
                self.assertEqual(self.inventory(query=query, source="x", stage="completed")["jobs"][0]["id"], self.x.id)
        self.assertEqual(self.inventory(job_id=self.youtube.id)["total"], 1)
        self.assertEqual(self.inventory(job_id=self.youtube.id, source="x")["total"], 0)
        self.assertEqual(self.inventory(stage="failed")["total"], 0)

    def test_json_command_has_only_json_and_never_initializes_storage(self):
        before = self.path.read_bytes()
        code, output, error = self.cli(["list", "--query", "Lauren", "--source", "x", "--json"])
        self.assertEqual(code, 0, error)
        inventory = json.loads(output)
        self.assertEqual(inventory["total"], 1)
        self.assertEqual(inventory["jobs"][0]["id"], self.x.id)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(error, "")

    def test_show_reads_transcript_and_derived_utterances_without_writes(self):
        before = self.path.read_bytes()
        code, output, error = self.cli(["show", "--id", self.x.id, "--json"])
        self.assertEqual(code, 0, error)
        result = json.loads(output)
        self.assertEqual(result["storage"]["path"], str(self.path.resolve()))
        self.assertEqual(result["job"]["source"], "x")
        transcript = result["job"]["transcript"]
        self.assertEqual(transcript["transcript_text"], "Source words")
        self.assertEqual(transcript["metadata"], {})
        self.assertEqual(transcript["utterances"][0]["text"], "Source words")
        self.assertEqual(transcript["utterances"][0]["start"], 1000)
        self.assertEqual(self.path.read_bytes(), before)
        code, output, error = self.cli(["show", "--id", self.x.id])
        self.assertEqual(code, 0, error)
        self.assertIn("Source words", output)

    def test_show_reports_missing_jobs_transcripts_and_required_id(self):
        for job_id, message in (("missing", "Job not found"), (self.youtube.id, "No saved transcript")):
            code, output, error = self.cli(["show", "--id", job_id, "--json"])
            self.assertEqual(code, 1)
            self.assertEqual(output, "")
            self.assertIn(message, error)
        code, output, error = self.cli(["show", "--json"])
        self.assertEqual(code, 2)
        code, output, error = self.cli(["show", "--help"], storage_path=self.root / "missing.db")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "missing.db").exists())

    def test_show_json_backend_reads_json_and_text_exports(self):
        for suffix in ("json", "txt"):
            export = self.root / f"transcript.{suffix}"
            content = {"transcript_text": "Hello", "words": [{"text": "Hello", "start": 0, "end": 1000}]}
            export.write_text(json.dumps(content) if suffix == "json" else "Hello")
            job = self.x.to_dict()
            job["transcript_file"] = str(export)
            state = self.root / "state.json"
            state.write_text(json.dumps({"jobs": {job["id"]: job}}))
            files_before = set(self.root.iterdir())
            code, output, error = self.cli(["show", "--id", self.x.id, "--json"], storage_path=state, backend="json")
            self.assertEqual(code, 0, error)
            transcript = json.loads(output)["job"]["transcript"]
            self.assertEqual(transcript["transcript_text"], "Hello")
            self.assertEqual(transcript["storage"], "file")
            self.assertEqual(set(self.root.iterdir()), files_before)

    def test_table_preserves_full_title_ids_and_platforms(self):
        code, output, error = self.cli(["list"])
        self.assertEqual(code, 0, error)
        self.assertIn(self.title, output)
        self.assertIn(self.x.id, output)
        self.assertIn(self.youtube.id, output)
        self.assertIn("youtube", output)
        self.assertIn("Not created", output)
        self.assertIn("Failed", output)

    def test_removed_flag_and_list_help_do_not_initialize_storage(self):
        code, output, error = self.cli(["--status"])
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments: --status", error)
        code, output, error = self.cli(["list", "--help"], storage_path=self.root / "missing.db")
        self.assertEqual(code, 0)
        self.assertIn("--source", output)
        self.assertFalse((self.root / "missing.db").exists())

    def test_missing_database_does_not_create_a_file_or_directory(self):
        missing = self.root / "missing" / "records.db"
        code, output, error = self.cli(["list", "--json"], storage_path=missing)
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("Storage file not found", error)
        self.assertFalse(missing.parent.exists())

    def test_default_path_resolution_does_not_create_data_directory(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, {"STORAGE_PATH": "", "STORAGE_BACKEND": "sqlite"}), \
                    patch("transcripts.config.load_config"):
                with self.assertRaises(FileNotFoundError):
                    list_inventory()
            self.assertFalse((self.root / "data").exists())
        finally:
            os.chdir(previous)

    def test_symlinked_storage_reports_the_resolved_path(self):
        link = self.root / "linked.db"
        link.symlink_to(self.path)
        inventory = list_inventory(backend="sqlite", storage_path=str(link))
        self.assertEqual(inventory["storage"]["path"], str(self.path.resolve()))

    def test_committed_wal_records_are_visible_without_checkpointing(self):
        writer = sqlite3.connect(self.path)
        self.addCleanup(writer.close)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE jobs SET title = ? WHERE id = ?", ("Newly committed title", self.x.id))
        writer.commit()
        wal = Path(str(self.path) + "-wal")
        self.assertTrue(wal.is_file())
        database_before, wal_before = self.path.read_bytes(), wal.read_bytes()
        jobs = self.inventory(query="Newly committed")["jobs"]
        self.assertEqual([job["id"] for job in jobs], [self.x.id])
        self.assertEqual(self.path.read_bytes(), database_before)
        self.assertEqual(wal.read_bytes(), wal_before)

    def test_legacy_sqlite_is_read_without_creating_missing_feature_tables(self):
        path = self.root / "legacy.db"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE jobs (id TEXT, url TEXT, title TEXT, stage TEXT, updated_at TEXT)")
            connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?)", (self.youtube.id, self.youtube.url, "Legacy", "completed", "2026-01-01"))
        before = path.read_bytes()
        inventory = list_inventory(backend="sqlite", storage_path=str(path))
        self.assertFalse(inventory["jobs"][0]["transcript"]["available"])
        self.assertEqual(inventory["jobs"][0]["navigation"]["topics"]["status"], "not_created")
        self.assertEqual(path.read_bytes(), before)

    def test_json_backend_reads_exports_without_creating_lock_files(self):
        export = self.root / "transcript.json"
        export.write_text(json.dumps({"duration": 8.5, "words": [{"text": "Hello", "start": 0, "end": 1000}]}))
        job = self.x.to_dict()
        job["transcript_file"] = str(export)
        state = self.root / "state.json"
        state.write_text(json.dumps({"version": 1, "jobs": {job["id"]: job}}))
        files_before = set(self.root.iterdir())
        state_before = state.read_bytes()
        code, output, error = self.cli(["list", "--json"], storage_path=state, backend="json")
        self.assertEqual(code, 0, error)
        item = json.loads(output)["jobs"][0]
        self.assertTrue(item["transcript"]["available"])
        self.assertEqual(item["transcript"]["word_count"], 1)
        self.assertEqual(item["transcript"]["storage"], "file")
        self.assertEqual(item["navigation"]["topics"]["status"], "not_supported")
        self.assertEqual(set(self.root.iterdir()), files_before)
        self.assertEqual(state.read_bytes(), state_before)

    def test_existing_url_transcription_dispatch_is_preserved(self):
        with patch("sys.argv", ["transcribe", self.youtube.url]), \
                patch("transcripts.cli.main.StateManager") as state, \
                patch("transcripts.cli.main.TranscriptProcessor") as processor, \
                redirect_stdout(io.StringIO()):
            processor.return_value.process_video.return_value = Transcript(self.youtube.url, "Title")
            main()
        state.assert_called_once_with()
        processor.return_value.process_video.assert_called_once_with(
            self.youtube.url, download_video=True, extract_audio=True,
        )


if __name__ == "__main__":
    unittest.main()
