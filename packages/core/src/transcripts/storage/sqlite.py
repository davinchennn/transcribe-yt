"""SQLite storage backend for job persistence and transcript storage."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from transcripts.models import Job, Stage, Transcript, Word, Utterance, derive_utterances, Analysis, AnalysisStatus, NavigationAnalysis
from transcripts.storage.base import StorageBackend, extract_video_id


class _ClosingConnection(sqlite3.Connection):
    """Commit/rollback a context-managed transaction and then release its handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class SQLiteStorage(StorageBackend):
    """SQLite-based storage backend.

    Provides better concurrent access support than JSON file storage.
    Uses WAL mode for improved read performance.
    """

    def __init__(self, db_path: str = ".transcripts.db"):
        """Initialize SQLite storage.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path, factory=_ClosingConnection)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            # Enable WAL mode for better concurrent reads
            conn.execute("PRAGMA journal_mode=WAL")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT 'pending',
                    title TEXT,
                    error TEXT,
                    provider TEXT,
                    video_file TEXT,
                    audio_file TEXT,
                    transcript_file TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_stage ON jobs(stage)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at)
            """)

            # Migration: Add keep_video and keep_audio columns if they don't exist
            cursor = conn.execute("PRAGMA table_info(jobs)")
            columns = [row[1] for row in cursor.fetchall()]
            if "keep_video" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN keep_video INTEGER DEFAULT 1")
            if "keep_audio" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN keep_audio INTEGER DEFAULT 1")

            # Transcripts table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE NOT NULL,
                    video_url TEXT NOT NULL,
                    title TEXT,
                    duration REAL,
                    transcript_text TEXT NOT NULL,
                    words TEXT,
                    utterances TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transcripts_job_id ON transcripts(job_id)
            """)

            # FTS5 full-text search virtual table
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
                    title,
                    transcript_text,
                    content='transcripts',
                    content_rowid='id'
                )
            """)

            # Triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
                    INSERT INTO transcripts_fts(rowid, title, transcript_text)
                    VALUES (new.id, new.title, new.transcript_text);
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS transcripts_ad AFTER DELETE ON transcripts BEGIN
                    INSERT INTO transcripts_fts(transcripts_fts, rowid, title, transcript_text)
                    VALUES('delete', old.id, old.title, old.transcript_text);
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS transcripts_au AFTER UPDATE ON transcripts BEGIN
                    INSERT INTO transcripts_fts(transcripts_fts, rowid, title, transcript_text)
                    VALUES('delete', old.id, old.title, old.transcript_text);
                    INSERT INTO transcripts_fts(rowid, title, transcript_text)
                    VALUES (new.id, new.title, new.transcript_text);
                END
            """)

            # Analyses table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    summary TEXT,
                    key_points TEXT,
                    model TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS navigation_analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    view TEXT NOT NULL CHECK(view IN ('timeline', 'topics')),
                    status TEXT NOT NULL DEFAULT 'pending',
                    summary TEXT,
                    nodes TEXT NOT NULL DEFAULT '[]',
                    model TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(job_id, view),
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                )
            """)

            conn.commit()

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        """Convert a database row to a Job object."""
        # Handle both old schema (no keep_video/keep_audio) and new schema
        keep_video = row["keep_video"] if "keep_video" in row.keys() else True
        keep_audio = row["keep_audio"] if "keep_audio" in row.keys() else True
        return Job(
            id=row["id"],
            url=row["url"],
            stage=Stage(row["stage"]),
            title=row["title"],
            error=row["error"],
            provider=row["provider"],
            video_file=row["video_file"],
            audio_file=row["audio_file"],
            transcript_file=row["transcript_file"],
            keep_video=bool(keep_video),
            keep_audio=bool(keep_audio),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by video ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_job(row)
            return None

    def get_job_by_url(self, url: str) -> Optional[Job]:
        """Get a job by URL."""
        video_id = extract_video_id(url)
        if video_id:
            return self.get_job(video_id)
        return None

    def create_job(self, url: str) -> Job:
        """Create a new job or return existing one."""
        video_id = extract_video_id(url)
        if not video_id:
            raise ValueError(f"Unsupported video URL. Use a YouTube video or X post URL: {url}")

        # Check for existing job first
        existing = self.get_job(video_id)
        if existing:
            return existing

        # Create new job
        now = datetime.utcnow().isoformat()
        job = Job(id=video_id, url=url, created_at=now, updated_at=now)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, url, stage, title, error, provider,
                                  video_file, audio_file, transcript_file,
                                  keep_video, keep_audio,
                                  created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.url,
                    job.stage.value,
                    job.title,
                    job.error,
                    job.provider,
                    job.video_file,
                    job.audio_file,
                    job.transcript_file,
                    1 if job.keep_video else 0,
                    1 if job.keep_audio else 0,
                    job.created_at,
                    job.updated_at,
                ),
            )
            conn.commit()

        return job

    def update_job(self, job: Job) -> None:
        """Update an existing job."""
        job.updated_at = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    url = ?,
                    stage = ?,
                    title = ?,
                    error = ?,
                    provider = ?,
                    video_file = ?,
                    audio_file = ?,
                    transcript_file = ?,
                    keep_video = ?,
                    keep_audio = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    job.url,
                    job.stage.value,
                    job.title,
                    job.error,
                    job.provider,
                    job.video_file,
                    job.audio_file,
                    job.transcript_file,
                    1 if job.keep_video else 0,
                    1 if job.keep_audio else 0,
                    job.updated_at,
                    job.id,
                ),
            )
            conn.commit()

    def set_stage(
        self, job_id: str, stage: Stage, error: Optional[str] = None
    ) -> Optional[Job]:
        """Update job stage."""
        job = self.get_job(job_id)
        if not job:
            return None

        job.stage = stage
        job.updated_at = datetime.utcnow().isoformat()

        if stage == Stage.FAILED and error:
            job.error = error
        elif stage != Stage.FAILED:
            job.error = None

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE jobs SET stage = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (job.stage.value, job.error, job.updated_at, job_id),
            )
            conn.commit()

        return job

    def list_jobs(self, filter_stage: Optional[Stage] = None) -> List[Job]:
        """List all jobs, optionally filtered by stage."""
        with self._get_connection() as conn:
            if filter_stage:
                cursor = conn.execute(
                    """
                    SELECT * FROM jobs WHERE stage = ?
                    ORDER BY updated_at DESC
                    """,
                    (filter_stage.value,),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM jobs ORDER BY updated_at DESC"
                )

            return [self._row_to_job(row) for row in cursor.fetchall()]

    def get_failed_jobs(self) -> List[Job]:
        """Get all failed jobs."""
        return self.list_jobs(filter_stage=Stage.FAILED)

    def delete_job(self, job_id: str) -> bool:
        """Delete a single job by ID."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM navigation_analyses WHERE job_id = ?", (job_id,))
            cursor = conn.execute(
                "DELETE FROM jobs WHERE id = ?", (job_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_jobs(self, filter_stage: Optional[Stage] = None) -> int:
        """Clear jobs from state."""
        with self._get_connection() as conn:
            if filter_stage:
                conn.execute(
                    "DELETE FROM navigation_analyses WHERE job_id IN (SELECT id FROM jobs WHERE stage = ?)",
                    (filter_stage.value,),
                )
                cursor = conn.execute(
                    "DELETE FROM jobs WHERE stage = ?",
                    (filter_stage.value,),
                )
            else:
                conn.execute("DELETE FROM navigation_analyses")
                cursor = conn.execute("DELETE FROM jobs")

            conn.commit()
            return cursor.rowcount

    def verify_stage_files(self, job: Job) -> Stage:
        """Verify intermediate files exist and return adjusted stage."""
        # If job is pending or failed, no adjustment needed
        if job.stage in (Stage.PENDING, Stage.FAILED):
            return job.stage

        # Check files based on stage progression
        stage_order = [
            Stage.PENDING,
            Stage.DOWNLOADING,
            Stage.EXTRACTING,
            Stage.TRANSCRIBING,
            Stage.SAVING,
            Stage.COMPLETED,
        ]

        current_index = (
            stage_order.index(job.stage) if job.stage in stage_order else 0
        )

        # If past downloading, verify video file
        if current_index >= stage_order.index(Stage.EXTRACTING):
            if job.video_file and not Path(job.video_file).exists():
                return Stage.PENDING

        # If past extracting, verify audio file
        if current_index >= stage_order.index(Stage.TRANSCRIBING):
            if job.audio_file and not Path(job.audio_file).exists():
                # Video might still exist, restart from extracting
                if job.video_file and Path(job.video_file).exists():
                    return Stage.DOWNLOADING  # Will re-extract
                return Stage.PENDING

        # If completed, verify transcript file
        if job.stage == Stage.COMPLETED:
            if job.transcript_file and not Path(job.transcript_file).exists():
                # Audio might still exist, restart from transcribing
                if job.audio_file and Path(job.audio_file).exists():
                    return Stage.EXTRACTING
                if job.video_file and Path(job.video_file).exists():
                    return Stage.DOWNLOADING
                return Stage.PENDING

        return job.stage

    # -------------------------------------------------------------------------
    # Transcript Methods
    # -------------------------------------------------------------------------

    def save_transcript(self, job_id: str, transcript: Transcript) -> None:
        """Save transcript to database.

        Args:
            job_id: Job ID to link transcript to
            transcript: Transcript object to save

        Note:
            Utterances are not saved - they are derived from words on retrieval.
        """
        # Serialize words to JSON (utterances are derived on-the-fly, not stored)
        words_json = json.dumps(
            [
                {
                    "text": w.text,
                    "start": w.start,
                    "end": w.end,
                    "confidence": w.confidence,
                    "speaker": w.speaker,
                }
                for w in transcript.words
            ]
        ) if transcript.words else None

        metadata_json = json.dumps(transcript.metadata) if transcript.metadata else None

        with self._get_connection() as conn:
            # Compare and invalidate in the same write transaction so a source
            # replacement cannot leave navigation anchored to older word times.
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute(
                "SELECT transcript_text, words FROM transcripts WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if previous is not None and (
                previous["transcript_text"] != transcript.transcript_text
                or previous["words"] != words_json
            ):
                conn.execute("DELETE FROM navigation_analyses WHERE job_id = ?", (job_id,))
            conn.execute(
                """
                INSERT OR REPLACE INTO transcripts
                (job_id, video_url, title, duration, transcript_text,
                 words, utterances, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    transcript.video_url,
                    transcript.title,
                    transcript.duration,
                    transcript.transcript_text,
                    words_json,
                    None,  # utterances - derived on retrieval, not stored
                    metadata_json,
                    transcript.created_at,
                ),
            )
            conn.commit()

    def get_transcript(self, job_id: str) -> Optional[Transcript]:
        """Get transcript by job ID.

        Args:
            job_id: Job ID to look up

        Returns:
            Transcript object if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM transcripts WHERE job_id = ?", (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_transcript(row)

    def _row_to_transcript(self, row: sqlite3.Row) -> Transcript:
        """Convert database row to Transcript object.

        Note:
            Utterances are derived from words, not read from database.
            This supports both old records (with stored utterances) and
            new records (utterances derived on-the-fly).
        """
        # Deserialize words
        words = []
        if row["words"]:
            words_data = json.loads(row["words"])
            words = [
                Word(
                    text=w["text"],
                    start=w["start"],
                    end=w["end"],
                    confidence=w.get("confidence"),
                    speaker=w.get("speaker"),
                )
                for w in words_data
            ]

        # Derive utterances from words (don't read from database)
        utterances = derive_utterances(words)

        # Deserialize metadata
        metadata = {}
        if row["metadata"]:
            metadata = json.loads(row["metadata"])

        return Transcript(
            video_url=row["video_url"],
            title=row["title"] or "",
            duration=row["duration"],
            transcript_text=row["transcript_text"],
            words=words,
            utterances=utterances,
            created_at=row["created_at"],
            metadata=metadata,
        )

    def list_transcripts(self) -> List[Transcript]:
        """List all transcripts.

        Returns:
            List of Transcript objects, sorted by created_at descending
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM transcripts ORDER BY created_at DESC"
            )
            return [self._row_to_transcript(row) for row in cursor.fetchall()]

    def delete_transcript(self, job_id: str) -> bool:
        """Delete transcript by job ID.

        Args:
            job_id: Job ID to delete transcript for

        Returns:
            True if deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM transcripts WHERE job_id = ?", (job_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def search_transcripts(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search transcripts using full-text search.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of dicts with: job_id, title, snippet, rank
        """
        with self._get_connection() as conn:
            # Use FTS5 MATCH with snippet() for context
            cursor = conn.execute(
                """
                SELECT
                    t.job_id,
                    t.title,
                    snippet(transcripts_fts, 1, '<mark>', '</mark>', '...', 32) as snippet,
                    bm25(transcripts_fts) as rank
                FROM transcripts_fts
                JOIN transcripts t ON transcripts_fts.rowid = t.id
                WHERE transcripts_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )

            results = []
            for row in cursor.fetchall():
                results.append({
                    "job_id": row["job_id"],
                    "title": row["title"],
                    "snippet": row["snippet"],
                    "rank": row["rank"],
                })

            return results

    # -------------------------------------------------------------------------
    # Analysis Methods
    # -------------------------------------------------------------------------

    def save_analysis(self, analysis: Analysis) -> None:
        """Save or update an analysis in the database."""
        analysis.updated_at = datetime.utcnow().isoformat()
        key_points_json = json.dumps(analysis.key_points) if analysis.key_points else None

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO analyses
                (job_id, status, summary, key_points, model, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.job_id,
                    analysis.status.value,
                    analysis.summary,
                    key_points_json,
                    analysis.model,
                    analysis.error,
                    analysis.created_at,
                    analysis.updated_at,
                ),
            )
            conn.commit()

    def get_analysis(self, job_id: str) -> Optional[Analysis]:
        """Get analysis by job ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM analyses WHERE job_id = ?", (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            key_points = []
            if row["key_points"]:
                key_points = json.loads(row["key_points"])

            return Analysis(
                job_id=row["job_id"],
                status=AnalysisStatus(row["status"]),
                summary=row["summary"],
                key_points=key_points,
                model=row["model"],
                error=row["error"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def delete_analysis(self, job_id: str) -> bool:
        """Delete analysis by job ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM analyses WHERE job_id = ?", (job_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    # Timeline and topic navigation are created and cached independently.

    def save_navigation(self, analysis: NavigationAnalysis) -> None:
        """Save a navigation result without replacing the other view."""
        if analysis.view not in ("timeline", "topics"):
            raise ValueError("Navigation view must be 'timeline' or 'topics'")
        analysis.updated_at = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO navigation_analyses
                (job_id, view, status, summary, nodes, model, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, view) DO UPDATE SET
                    status = excluded.status, summary = excluded.summary,
                    nodes = excluded.nodes, model = excluded.model,
                    error = excluded.error, updated_at = excluded.updated_at
                """,
                (analysis.job_id, analysis.view, analysis.status.value,
                 analysis.summary, json.dumps(analysis.nodes), analysis.model,
                 analysis.error, analysis.created_at, analysis.updated_at),
            )
            analysis.created_at = conn.execute(
                "SELECT created_at FROM navigation_analyses WHERE job_id = ? AND view = ?",
                (analysis.job_id, analysis.view),
            ).fetchone()["created_at"]
            conn.commit()

    def get_navigation(self, job_id: str, view: str) -> Optional[NavigationAnalysis]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM navigation_analyses WHERE job_id = ? AND view = ?",
                (job_id, view),
            ).fetchone()
            if row is None:
                return None
            data = dict(row)
            data["nodes"] = json.loads(row["nodes"])
            return NavigationAnalysis.from_dict(data)

    def save_navigation_if_current(
        self, updated: NavigationAnalysis, expected: NavigationAnalysis, transcript: Transcript
    ) -> bool:
        """Atomically replace only subtopic summaries if cache and source match.

        The source snapshot must come from get_transcript, whose utterances are
        derived from stored words. Deleted or changed caches are never recreated.
        """
        previous = expected.to_dict()
        replacement = updated.to_dict()
        if expected.view not in ("timeline", "topics") or expected.status != AnalysisStatus.COMPLETED:
            raise ValueError("Summary updates require a completed navigation view")
        if any(previous[key] != replacement[key] for key in previous if key not in ("nodes", "updated_at")):
            raise ValueError("Summary updates must preserve navigation metadata")
        pending = [(expected.nodes, updated.nodes, 0)]
        while pending:
            old_nodes, new_nodes, depth = pending.pop()
            if len(old_nodes) != len(new_nodes):
                raise ValueError("Summary updates must preserve navigation hierarchy")
            for old, new in zip(old_nodes, new_nodes):
                ignored = {"children", "summary"} if depth else {"children"}
                if {key: value for key, value in old.items() if key not in ignored} != {
                    key: value for key, value in new.items() if key not in ignored
                }:
                    raise ValueError("Summary updates must preserve roots and source references")
                pending.append((old.get("children", []), new.get("children", []), depth + 1))

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT * FROM navigation_analyses WHERE job_id = ? AND view = ?
                   AND EXISTS (SELECT 1 FROM jobs WHERE id = ?)""",
                (expected.job_id, expected.view, expected.job_id),
            ).fetchone()
            source_row = conn.execute(
                "SELECT * FROM transcripts WHERE job_id = ?", (expected.job_id,),
            ).fetchone()
            if row is None or source_row is None:
                return False
            current = dict(row)
            current["nodes"] = json.loads(row["nodes"])
            if NavigationAnalysis.from_dict(current).to_dict() != previous:
                return False
            source = self._row_to_transcript(source_row)
            if (
                source.transcript_text != transcript.transcript_text
                or source.words != transcript.words
                or source.utterances != transcript.utterances
            ):
                return False
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE navigation_analyses SET nodes = ?, updated_at = ? WHERE job_id = ? AND view = ?",
                (json.dumps(updated.nodes), now, expected.job_id, expected.view),
            )
            conn.commit()
        updated.updated_at = now
        return True

    def claim_navigation(self, job_id: str, view: str) -> bool:
        """Atomically reserve a view, allowing failed or abandoned requests to retry.

        A live request refreshes its lease with lease_navigation. Reservations
        untouched for 15 minutes can be recovered after an API restart.
        """
        if view not in ("timeline", "topics"):
            raise ValueError("Navigation view must be 'timeline' or 'topics'")
        now = datetime.utcnow().isoformat()
        stale_before = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO navigation_analyses
                (job_id, view, status, nodes, created_at, updated_at)
                SELECT ?, ?, 'processing', '[]', ?, ?
                WHERE EXISTS (SELECT 1 FROM jobs WHERE id = ?)
                ON CONFLICT(job_id, view) DO UPDATE SET
                    status = 'processing', error = NULL, updated_at = excluded.updated_at
                WHERE navigation_analyses.status = 'failed'
                    OR (navigation_analyses.status IN ('pending', 'processing')
                        AND navigation_analyses.updated_at < ?)
                """,
                (job_id, view, now, now, job_id, stale_before),
            )
            conn.commit()
            return cursor.rowcount > 0

    def lease_navigation(self, job_id: str, view: str) -> bool:
        """Refresh an existing processing reservation without recreating deleted rows."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """UPDATE navigation_analyses SET updated_at = ?
                   WHERE job_id = ? AND view = ? AND status = 'processing'""",
                (datetime.utcnow().isoformat(), job_id, view),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_navigation(self, job_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM navigation_analyses WHERE job_id = ?", (job_id,))
            conn.commit()
            return cursor.rowcount > 0
