"""SQLite storage backend for job persistence and transcript storage."""

import json
import hashlib
import sqlite3
from uuid import NAMESPACE_URL, uuid4, uuid5
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from transcripts.models import Job, Stage, Transcript, Word, Utterance, derive_utterances, AnalysisStatus, SavedAnalysis
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

            self._init_saved_analyses(conn)
            conn.commit()

    @staticmethod
    def _transcript_hash(transcript: Transcript) -> str:
        source = {
            "text": transcript.transcript_text,
            "words": [vars(word) for word in transcript.words],
            "utterances": [vars(turn) for turn in transcript.utterances],
        }
        return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def _init_saved_analyses(self, conn: sqlite3.Connection) -> None:
        """Verify lossless imports before removing the old per-job result tables."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS video_analyses (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                name TEXT NOT NULL,
                view TEXT CHECK(view IS NULL OR view IN ('timeline', 'topics')),
                prompt TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                summary TEXT,
                key_points TEXT NOT NULL DEFAULT '[]',
                nodes TEXT NOT NULL DEFAULT '[]',
                provider TEXT,
                model TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_hash TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_video_analyses_job_created ON video_analyses(job_id, created_at DESC)")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        conn.execute("BEGIN IMMEDIATE")
        self._remove_stored_utterances(conn)
        original_migration = "saved_analysis_versions_v1"
        applied = conn.execute("SELECT applied_at FROM schema_migrations WHERE name = ?", (original_migration,)).fetchone()
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in ("analyses", "navigation_analyses"):
            if table not in tables:
                continue
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            for row in rows:
                data = dict(row)
                view = data.get("view") if table == "navigation_analyses" else None
                analysis_id = str(uuid5(NAMESPACE_URL, f"transcribe-yt:{table}:{data['job_id']}:{data['id']}"))
                source = conn.execute("SELECT * FROM transcripts WHERE job_id = ?", (data["job_id"],)).fetchone()
                source_hash = self._transcript_hash(self._row_to_transcript(source)) if source else None
                expected = SavedAnalysis(
                    id=analysis_id, job_id=data["job_id"], name=view.title() if view else "General summary",
                    view=view, status=AnalysisStatus(data["status"]), summary=data.get("summary"),
                    key_points=json.loads(data.get("key_points") or "[]") if view is None else [],
                    nodes=json.loads(data.get("nodes") or "[]") if view else [],
                    provider=data.get("provider", "kimi"), model=data.get("model"), error=data.get("error"),
                    created_at=data["created_at"], updated_at=data["updated_at"],
                )
                if not isinstance(expected.key_points, list) or not isinstance(expected.nodes, list):
                    raise ValueError(f"Cannot migrate invalid legacy analysis arrays in {table}/{data['id']}")
                copied = conn.execute("SELECT * FROM video_analyses WHERE id = ?", (analysis_id,)).fetchone()
                if applied and copied is None and expected.created_at <= applied["applied_at"]:
                    if expected.updated_at > applied["applied_at"]:
                        raise ValueError(
                            f"Cannot verify changed legacy result {table}/{data['id']}: its original version is missing"
                        )
                    # The first migration already copied this old result. Its
                    # missing immutable version represents an intentional deletion.
                    continue
                if copied is not None and self._row_to_saved_analysis(copied).to_dict() != expected.to_dict():
                    # Old endpoints could change their cache after the first copy.
                    # Preserve that newer legacy state as another immutable version.
                    content = expected.to_dict()
                    content.pop("id")
                    digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    expected.id = str(uuid5(NAMESPACE_URL, f"transcribe-yt:legacy-revision:{analysis_id}:{digest}"))
                    copied = conn.execute("SELECT * FROM video_analyses WHERE id = ?", (expected.id,)).fetchone()
                if copied is None:
                    self._insert_imported_analysis(conn, expected, source_hash)
                    copied = conn.execute("SELECT * FROM video_analyses WHERE id = ?", (expected.id,)).fetchone()
                if copied is None or self._row_to_saved_analysis(copied).to_dict() != expected.to_dict():
                    raise ValueError(f"Legacy analysis verification failed for {table}/{data['id']}")
            conn.execute(f"DROP TABLE {table}")
        now = datetime.utcnow().isoformat()
        conn.execute("INSERT OR IGNORE INTO schema_migrations (name, applied_at) VALUES (?, ?)", (original_migration, now))
        conn.execute("INSERT OR IGNORE INTO schema_migrations (name, applied_at) VALUES (?, ?)", ("saved_analysis_cleanup_v2", now))

    @staticmethod
    def _remove_stored_utterances(conn: sqlite3.Connection) -> None:
        """Keep legacy turn data in supported metadata before dropping its column."""
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(transcripts)")}
        if "utterances" not in columns:
            return
        for row in conn.execute("SELECT id, utterances, metadata FROM transcripts WHERE utterances IS NOT NULL").fetchall():
            turns = json.loads(row["utterances"])
            metadata = json.loads(row["metadata"] or "{}")
            if not isinstance(turns, list) or not isinstance(metadata, dict):
                raise ValueError(f"Cannot preserve invalid stored utterances for transcript {row['id']}")
            if "_stored_utterances" in metadata and metadata["_stored_utterances"] != turns:
                raise ValueError(f"Stored utterances conflict with metadata for transcript {row['id']}")
            metadata["_stored_utterances"] = turns
            conn.execute("UPDATE transcripts SET metadata = ? WHERE id = ?", (json.dumps(metadata), row["id"]))
        conn.execute("ALTER TABLE transcripts DROP COLUMN utterances")

    @staticmethod
    def _metadata_utterances(metadata: Dict[str, Any]) -> List[Utterance]:
        turns = metadata.get("_stored_utterances") or []
        if not isinstance(turns, list):
            raise ValueError("Stored transcript utterances must be a JSON array")
        return [Utterance(speaker=turn["speaker"], text=turn["text"], start=turn["start"],
                          end=turn["end"], confidence=turn.get("confidence")) for turn in turns]

    @staticmethod
    def _insert_imported_analysis(conn: sqlite3.Connection, analysis: SavedAnalysis, source_hash: Optional[str]) -> None:
        conn.execute("""
            INSERT INTO video_analyses
            (id, job_id, name, view, prompt, status, summary, key_points, nodes,
             provider, model, error, created_at, updated_at, source_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (analysis.id, analysis.job_id, analysis.name, analysis.view, analysis.prompt,
              analysis.status.value, analysis.summary, json.dumps(analysis.key_points), json.dumps(analysis.nodes),
              analysis.provider, analysis.model, analysis.error, analysis.created_at, analysis.updated_at, source_hash))

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
            conn.execute("DELETE FROM video_analyses WHERE job_id = ?", (job_id,))
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
                    "DELETE FROM video_analyses WHERE job_id IN (SELECT id FROM jobs WHERE stage = ?)",
                    (filter_stage.value,),
                )
                cursor = conn.execute(
                    "DELETE FROM jobs WHERE stage = ?",
                    (filter_stage.value,),
                )
            else:
                conn.execute("DELETE FROM video_analyses")
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

        Utterances are derived from words. Utterance-only source data is retained
        in metadata so removing the redundant column does not lose old timings.
        """
        # Word timings supply derived turns; utterance-only data uses metadata.
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

        metadata = dict(transcript.metadata)
        if not transcript.words and transcript.utterances and self._metadata_utterances(metadata) != transcript.utterances:
            metadata["_stored_utterances"] = [vars(turn) for turn in transcript.utterances]
        metadata_json = json.dumps(metadata) if metadata else None
        effective_source = Transcript(
            transcript.video_url, transcript.title, transcript_text=transcript.transcript_text,
            words=transcript.words,
            utterances=derive_utterances(transcript.words) if transcript.words else self._metadata_utterances(metadata),
        )

        with self._get_connection() as conn:
            # Compare and invalidate in the same write transaction so a source
            # replacement cannot leave navigation anchored to older word times.
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute(
                "SELECT * FROM transcripts WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if previous is not None and self._transcript_hash(self._row_to_transcript(previous)) != self._transcript_hash(effective_source):
                conn.execute("DELETE FROM video_analyses WHERE job_id = ?", (job_id,))
            conn.execute(
                """
                INSERT OR REPLACE INTO transcripts
                (job_id, video_url, title, duration, transcript_text,
                 words, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    transcript.video_url,
                    transcript.title,
                    transcript.duration,
                    transcript.transcript_text,
                    words_json,
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

        Word timings determine utterances when present; preserved turn data in
        metadata supplies the fallback for older utterance-only transcripts.
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

        # Deserialize metadata
        metadata = {}
        if row["metadata"]:
            metadata = json.loads(row["metadata"])

        utterances = derive_utterances(words) if words else self._metadata_utterances(metadata)

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
            conn.execute("DELETE FROM video_analyses WHERE job_id = ?", (job_id,))
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

    # Immutable named analysis versions.

    @staticmethod
    def _row_to_saved_analysis(row: sqlite3.Row) -> SavedAnalysis:
        values = dict(row)
        values["key_points"] = json.loads(values["key_points"] or "[]")
        values["nodes"] = json.loads(values["nodes"] or "[]")
        return SavedAnalysis.from_dict(values)

    def create_saved_analysis(
        self, job_id: str, name: str, view: str, prompt: str = "",
        provider: Optional[str] = None, model: Optional[str] = None,
    ) -> SavedAnalysis:
        """Reserve a new version; creating the same configuration never overwrites."""
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
            raise ValueError("Analysis name must contain 1-200 characters")
        if not isinstance(prompt, str) or len(prompt.strip()) > 10000:
            raise ValueError("Analysis prompt must contain at most 10000 characters")
        if view not in ("timeline", "topics"):
            raise ValueError("Analysis visualization must be 'timeline' or 'topics'")
        result = SavedAnalysis(id=str(uuid4()), job_id=job_id, name=name.strip(),
                               view=view, prompt=prompt.strip(), provider=provider, model=model)
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            job = conn.execute("SELECT stage FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                raise ValueError("Job not found")
            if job["stage"] != Stage.COMPLETED.value:
                raise ValueError("Only completed jobs can be analyzed")
            source = conn.execute("SELECT * FROM transcripts WHERE job_id = ?", (job_id,)).fetchone()
            if not source:
                raise ValueError("No transcript found for this job")
            source_hash = self._transcript_hash(self._row_to_transcript(source))
            conn.execute("""
                INSERT INTO video_analyses
                (id, job_id, name, view, prompt, status, provider, model, created_at, updated_at, source_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (result.id, result.job_id, result.name, result.view, result.prompt,
                  result.status.value, provider, model, result.created_at, result.updated_at, source_hash))
        return result

    def list_saved_analyses(self, job_id: str) -> List[SavedAnalysis]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM video_analyses WHERE job_id = ? ORDER BY created_at DESC, rowid DESC",
                                (job_id,)).fetchall()
            return [self._row_to_saved_analysis(row) for row in rows]

    def get_saved_analysis(self, job_id: str, analysis_id: str) -> Optional[SavedAnalysis]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM video_analyses WHERE job_id = ? AND id = ?",
                               (job_id, analysis_id)).fetchone()
            return self._row_to_saved_analysis(row) if row else None

    def delete_saved_analysis(self, job_id: str, analysis_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM video_analyses WHERE job_id = ? AND id = ?",
                                  (job_id, analysis_id))
            return cursor.rowcount > 0

    def claim_saved_analysis(
        self, job_id: str, analysis_id: str, transcript: Optional[Transcript] = None,
    ) -> bool:
        """Allow exactly one worker to start this reserved version."""
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("""
                SELECT source_hash FROM video_analyses
                WHERE job_id = ? AND id = ? AND status = 'pending'
            """, (job_id, analysis_id)).fetchone()
            if row is None:
                return False
            source = conn.execute("SELECT * FROM transcripts WHERE job_id = ?", (job_id,)).fetchone()
            if (
                source is None
                or row["source_hash"] != self._transcript_hash(self._row_to_transcript(source))
                or (transcript is not None and row["source_hash"] != self._transcript_hash(transcript))
            ):
                conn.execute("""
                    UPDATE video_analyses SET status = 'failed', error = ?, updated_at = ?
                    WHERE job_id = ? AND id = ?
                """, ("Transcript changed before analysis started. Create another analysis.",
                      datetime.utcnow().isoformat(), job_id, analysis_id))
                return False
            cursor = conn.execute("""
                UPDATE video_analyses SET status = 'processing', updated_at = ?
                WHERE job_id = ? AND id = ? AND status = 'pending'
                  AND EXISTS (SELECT 1 FROM jobs WHERE id = ? AND stage = 'completed')
            """, (datetime.utcnow().isoformat(), job_id, analysis_id, job_id))
            return cursor.rowcount > 0

    def finish_saved_analysis(self, result: SavedAnalysis, transcript: Transcript) -> bool:
        """Finish once, only while the reservation and original source still exist."""
        if result.status not in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED):
            raise ValueError("Finishing an analysis requires a completed or failed result")
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("""
                SELECT * FROM video_analyses WHERE job_id = ? AND id = ?
                  AND status IN ('pending', 'processing')
                  AND EXISTS (SELECT 1 FROM jobs WHERE id = ?)
            """, (result.job_id, result.id, result.job_id)).fetchone()
            source = conn.execute("SELECT * FROM transcripts WHERE job_id = ?", (result.job_id,)).fetchone()
            if not row or not source:
                return False
            if any(row[key] != getattr(result, key) for key in ("name", "view", "prompt", "created_at")):
                return False
            if any(row[key] is not None and row[key] != getattr(result, key) for key in ("provider", "model")):
                return False
            if (
                row["source_hash"] != self._transcript_hash(transcript)
                or row["source_hash"] != self._transcript_hash(self._row_to_transcript(source))
            ):
                return False
            now = datetime.utcnow().isoformat()
            conn.execute("""
                UPDATE video_analyses SET status = ?, summary = ?, key_points = ?, nodes = ?,
                    provider = ?, model = ?, error = ?, updated_at = ?
                WHERE job_id = ? AND id = ?
            """, (result.status.value, result.summary, json.dumps(result.key_points),
                  json.dumps(result.nodes), result.provider, result.model, result.error,
                  now, result.job_id, result.id))
        result.updated_at = now
        return True
