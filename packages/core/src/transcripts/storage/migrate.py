"""Migration utilities for converting between storage backends."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from transcripts.models import Job
from transcripts.storage.json import JSONStorage
from transcripts.storage.sqlite import SQLiteStorage


def migrate_json_to_sqlite(
    json_path: str = None,
    sqlite_path: str = None,
    backup: bool = True,
) -> int:
    """Migrate jobs from JSON storage to SQLite storage.

    Args:
        json_path: Path to the JSON state file. If None, checks legacy location.
        sqlite_path: Path to the SQLite database file. If None, uses default.
        backup: If True, create a backup of the JSON file after migration

    Returns:
        Number of jobs migrated

    Raises:
        FileNotFoundError: If JSON file doesn't exist
    """
    from transcripts.config import get_storage_path

    # Find JSON file - check legacy location first, then new location
    if json_path is None:
        legacy_path = Path(".transcripts-state.json")
        new_path = Path("data/state.json")
        if legacy_path.exists():
            json_path = str(legacy_path)
        elif new_path.exists():
            json_path = str(new_path)
        else:
            raise FileNotFoundError("No JSON state file found")

    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"JSON state file not found: {json_path}")

    # Use default SQLite path if not provided
    if sqlite_path is None:
        sqlite_path = get_storage_path("sqlite")

    # Load jobs from JSON
    json_storage = JSONStorage(state_file=json_path)
    jobs = json_storage.list_jobs()

    if not jobs:
        print("No jobs to migrate.")
        return 0

    # Create SQLite storage and migrate jobs
    sqlite_storage = SQLiteStorage(db_path=sqlite_path)

    migrated = 0
    for job in jobs:
        # Check if job already exists in SQLite
        existing = sqlite_storage.get_job(job.id)
        if existing:
            print(f"  Skipping {job.id} (already exists)")
            continue

        # Insert job into SQLite
        _insert_job_directly(sqlite_storage, job)
        migrated += 1
        print(f"  Migrated: {job.title or job.id}")

    # Create backup of JSON file
    if backup and migrated > 0:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = json_file.with_suffix(f".backup-{timestamp}.json")
        shutil.copy2(json_file, backup_path)
        print(f"\nBackup created: {backup_path}")

    return migrated


def _insert_job_directly(storage: SQLiteStorage, job: Job) -> None:
    """Insert a job directly into SQLite, preserving all fields.

    This bypasses create_job() to preserve original timestamps.
    """
    with storage._get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO jobs
            (id, url, stage, title, error, provider,
             video_file, audio_file, transcript_file,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                job.created_at,
                job.updated_at,
            ),
        )
        conn.commit()


def check_migration_needed(
    json_path: str = None,
    sqlite_path: str = None,
) -> Optional[int]:
    """Check if migration from JSON to SQLite is needed.

    Args:
        json_path: Path to the JSON state file. If None, checks legacy and new locations.
        sqlite_path: Path to the SQLite database file. If None, uses default.

    Returns:
        Number of jobs that would be migrated, or None if no migration needed
    """
    from transcripts.config import get_storage_path

    # Find JSON file - check legacy location first, then new location
    if json_path is None:
        legacy_path = Path(".transcripts-state.json")
        new_path = Path("data/state.json")
        if legacy_path.exists():
            json_file = legacy_path
        elif new_path.exists():
            json_file = new_path
        else:
            return None
    else:
        json_file = Path(json_path)

    # Use default SQLite path if not provided
    if sqlite_path is None:
        sqlite_path = get_storage_path("sqlite")
    sqlite_file = Path(sqlite_path)

    # No JSON file means nothing to migrate
    if not json_file.exists():
        return None

    # Load JSON jobs
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            json_jobs = data.get("jobs", {})
    except (json.JSONDecodeError, IOError):
        return None

    if not json_jobs:
        return None

    # If SQLite doesn't exist, all jobs need migration
    if not sqlite_file.exists():
        return len(json_jobs)

    # Check how many jobs are not in SQLite
    sqlite_storage = SQLiteStorage(db_path=sqlite_path)
    needs_migration = 0

    for job_id in json_jobs:
        if not sqlite_storage.get_job(job_id):
            needs_migration += 1

    return needs_migration if needs_migration > 0 else None
