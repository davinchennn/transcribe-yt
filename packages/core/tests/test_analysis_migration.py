"""Legacy result cleanup verifies preservation and rolls back on unsafe data."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from transcripts.models import AnalysisStatus, SavedAnalysis, Stage, Transcript, Word
from transcripts.storage.sqlite import SQLiteStorage


class AnalysisCleanupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "old.db"
        self.storage = SQLiteStorage(str(self.path))
        self.job = self.storage.create_job("https://youtu.be/abcdefghijk")
        self.storage.set_stage(self.job.id, Stage.COMPLETED)
        self.storage.save_transcript(self.job.id, Transcript(self.job.url, "Video", transcript_text="Spoken content",
                                                            words=[Word("Spoken", 0, 100), Word("content", 150, 250)]))

    def connection(self):
        return closing(sqlite3.connect(self.path))

    def legacy_schema(self, *, v1=False, provider=True):
        with self.connection() as conn, conn:
            conn.execute("DELETE FROM schema_migrations")
            if v1:
                conn.execute("INSERT INTO schema_migrations VALUES ('saved_analysis_versions_v1', '2026-01-01T00:00:00')")
            provider_column = ", provider TEXT" if provider else ""
            conn.execute(f"CREATE TABLE analyses (id INTEGER PRIMARY KEY, job_id TEXT, status TEXT, summary TEXT, key_points TEXT, model TEXT, error TEXT, created_at TEXT, updated_at TEXT{provider_column})")
            conn.execute(f"CREATE TABLE navigation_analyses (id INTEGER PRIMARY KEY, job_id TEXT, view TEXT, status TEXT, summary TEXT, nodes TEXT, model TEXT, error TEXT, created_at TEXT, updated_at TEXT{provider_column})")

    def legacy(self, *, table="analyses", row_id=1, summary="Original summary", view=None,
               created_at="2025-01-01T00:00:00", updated_at="2025-01-02T00:00:00", provider="fireworks"):
        result = SavedAnalysis(
            id=str(uuid5(NAMESPACE_URL, f"transcribe-yt:{table}:{self.job.id}:{row_id}")),
            job_id=self.job.id, name=view.title() if view else "General summary", view=view,
            status=AnalysisStatus.COMPLETED, summary=summary,
            key_points=["Original point"] if view is None else [],
            nodes=[{"id": "node", "summary": "Original node", "children": [], "occurrences": []}] if view else [],
            provider=provider, model="exact-model", created_at=created_at, updated_at=updated_at,
        )
        data = {"id": row_id, "job_id": result.job_id, "status": result.status.value, "summary": summary,
                "model": result.model, "error": None, "created_at": created_at, "updated_at": updated_at}
        data.update({"view": view, "nodes": json.dumps(result.nodes)} if view else {"key_points": json.dumps(result.key_points)})
        with self.connection() as conn, conn:
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "provider" in columns:
                data["provider"] = provider
            conn.execute(f"INSERT INTO {table} ({', '.join(data)}) VALUES ({', '.join('?' for _ in data)})", tuple(data.values()))
        return result

    def copied_version(self, record):
        data = record.to_dict()
        data["nodes"], data["key_points"] = json.dumps(record.nodes), json.dumps(record.key_points)
        with self.connection() as conn, conn:
            conn.execute(f"INSERT INTO video_analyses ({', '.join(data)}) VALUES ({', '.join('?' for _ in data)})", tuple(data.values()))

    def tables(self):
        with self.connection() as conn:
            return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def test_fresh_schema_has_only_canonical_analysis_storage(self):
        self.assertNotIn("analyses", self.tables())
        self.assertNotIn("navigation_analyses", self.tables())
        self.assertFalse(hasattr(self.storage, "save_analysis"))
        self.assertFalse(hasattr(self.storage, "get_navigation"))
        with self.connection() as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(transcripts)")}
            migrations = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
        self.assertNotIn("utterances", columns)
        self.assertIn("saved_analysis_cleanup_v2", migrations)

    def test_never_upgraded_missing_provider_schema_imports_and_verifies_all_fields(self):
        self.legacy_schema(provider=False)
        summary = self.legacy(provider="kimi")
        timeline = self.legacy(table="navigation_analyses", view="timeline", provider="kimi")
        storage = SQLiteStorage(str(self.path))
        self.assertEqual(storage.get_saved_analysis(self.job.id, summary.id).to_dict(), summary.to_dict())
        self.assertEqual(storage.get_saved_analysis(self.job.id, timeline.id).to_dict(), timeline.to_dict())
        self.assertNotIn("analyses", self.tables())
        self.assertNotIn("navigation_analyses", self.tables())

    def test_v1_missing_original_copy_stays_deleted(self):
        self.legacy_schema(v1=True)
        summary = self.legacy()
        deleted = self.legacy(table="navigation_analyses", view="topics")
        self.copied_version(summary)
        storage = SQLiteStorage(str(self.path))
        self.assertEqual([record.id for record in storage.list_saved_analyses(self.job.id)], [summary.id])
        self.assertIsNone(storage.get_saved_analysis(self.job.id, deleted.id))
        self.assertNotIn("navigation_analyses", self.tables())

    def test_v1_changed_old_cache_preserves_both_immutable_states(self):
        self.legacy_schema(v1=True)
        current = self.legacy(summary="New old-API result", updated_at="2026-01-02T00:00:00")
        original = SavedAnalysis.from_dict({**current.to_dict(), "summary": "Original copied result", "updated_at": "2025-01-02T00:00:00"})
        self.copied_version(original)
        storage = SQLiteStorage(str(self.path))
        versions = storage.list_saved_analyses(self.job.id)
        self.assertEqual(len(versions), 2)
        self.assertEqual({row.summary for row in versions}, {"Original copied result", "New old-API result"})
        self.assertEqual(storage.get_saved_analysis(self.job.id, original.id).to_dict(), original.to_dict())
        self.assertEqual(len(SQLiteStorage(str(self.path)).list_saved_analyses(self.job.id)), 2)

    def test_old_api_created_a_new_row_after_v1_copy(self):
        self.legacy_schema(v1=True)
        newer = self.legacy(row_id=20, created_at="2026-01-02T00:00:00", updated_at="2026-01-02T00:00:00")
        storage = SQLiteStorage(str(self.path))
        self.assertEqual(storage.get_saved_analysis(self.job.id, newer.id).to_dict(), newer.to_dict())

    def test_ambiguous_changed_missing_copy_blocks_cleanup_instead_of_losing_data(self):
        self.legacy_schema(v1=True)
        self.legacy(created_at="2025-01-01T00:00:00", updated_at="2026-01-02T00:00:00")
        with self.assertRaisesRegex(ValueError, "original version is missing"):
            SQLiteStorage(str(self.path))
        self.assertIn("analyses", self.tables())
        self.assertIn("navigation_analyses", self.tables())
        with self.connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM video_analyses").fetchone()[0], 0)
            self.assertIsNone(conn.execute("SELECT 1 FROM schema_migrations WHERE name = 'saved_analysis_cleanup_v2'").fetchone())

    def test_invalid_legacy_result_rolls_back_imports_drops_and_markers(self):
        self.legacy_schema()
        self.legacy()
        self.legacy(table="navigation_analyses", view="timeline")
        with self.connection() as conn, conn:
            conn.execute("UPDATE navigation_analyses SET nodes = '{}' ")
            conn.execute("ALTER TABLE transcripts ADD COLUMN utterances TEXT")
            conn.execute("UPDATE transcripts SET utterances = '[]'")
        with self.assertRaisesRegex(ValueError, "invalid legacy analysis arrays"):
            SQLiteStorage(str(self.path))
        self.assertIn("analyses", self.tables())
        self.assertIn("navigation_analyses", self.tables())
        with self.connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM video_analyses").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 0)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(transcripts)")}
        self.assertIn("utterances", columns)

    def test_stored_turns_survive_column_removal_and_remain_a_source_fallback(self):
        turns = [{"speaker": "A", "text": "Spoken content", "start": 10, "end": 500, "confidence": 0.9, "extra_original_field": "Preserved"}]
        with self.connection() as conn, conn:
            conn.execute("ALTER TABLE transcripts ADD COLUMN utterances TEXT")
            conn.execute("UPDATE transcripts SET words = NULL, utterances = ?, metadata = ?",
                         (json.dumps(turns), json.dumps({"description": "Original metadata"})))
        storage = SQLiteStorage(str(self.path))
        transcript = storage.get_transcript(self.job.id)
        self.assertEqual(transcript.metadata, {"description": "Original metadata", "_stored_utterances": turns})
        self.assertEqual(transcript.utterances[0].text, "Spoken content")
        self.assertEqual(transcript.utterances[0].confidence, 0.9)
        self.assertEqual(len(storage.search_transcripts("Spoken")), 1)
        reserved = storage.create_saved_analysis(self.job.id, "Turn source", "timeline")
        transcript.utterances[0].start += 10
        storage.save_transcript(self.job.id, transcript)
        self.assertIsNone(storage.get_saved_analysis(self.job.id, reserved.id))
        with self.connection() as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(transcripts)")}
        self.assertNotIn("utterances", columns)

    def test_metadata_collision_blocks_column_removal_without_overwriting_data(self):
        preserved = {"_stored_utterances": [{"speaker": "Different"}], "description": "Preserve"}
        with self.connection() as conn, conn:
            conn.execute("ALTER TABLE transcripts ADD COLUMN utterances TEXT")
            conn.execute("UPDATE transcripts SET utterances = '[]', metadata = ?", (json.dumps(preserved),))
        with self.assertRaisesRegex(ValueError, "conflict with metadata"):
            SQLiteStorage(str(self.path))
        with self.connection() as conn:
            row = conn.execute("SELECT utterances, metadata FROM transcripts").fetchone()
        self.assertEqual(row[0], "[]")
        self.assertEqual(json.loads(row[1]), preserved)


if __name__ == "__main__":
    unittest.main()
