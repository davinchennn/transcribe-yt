# Implementation Plan: Storage Abstraction

**Branch**: `004-storage-abstraction` | **Date**: 2026-01-31 | **Spec**: [spec.md](./spec.md)

## Summary

Abstract the storage layer to support multiple backends (SQLite and JSON). SQLite becomes the default for better concurrency support needed by the upcoming web UI. JSON backend preserved for backward compatibility.

## Technical Context

**Language/Version**: Python 3.8+
**Primary Dependencies**: Existing + sqlite3 (stdlib)
**Storage**: SQLite (default) or JSON file (configurable)
**Testing**: Manual CLI testing (pytest in PROPOSALS.md for future)
**Project Type**: Single project (monorepo core package)

## Project Structure

### Documentation (this feature)

```text
specs/004-storage-abstraction/
├── spec.md              # Feature specification
└── plan.md              # This file
```

### Source Code Changes

```text
packages/core/src/transcripts/
├── storage/                    # NEW - Storage abstraction package
│   ├── __init__.py             # Exports: StorageBackend, get_storage
│   ├── base.py                 # StorageBackend ABC + extract_video_id
│   ├── sqlite.py               # SQLiteStorage implementation
│   ├── json.py                 # JSONStorage (refactored from state.py)
│   └── migrate.py              # JSON → SQLite migration utility
├── state.py                    # MODIFY - Thin wrapper using get_storage()
├── config.py                   # MODIFY - Add storage config helpers
└── cli/main.py                 # MODIFY - Add --migrate flag (optional)
```

## Implementation Approach

### Phase 1: Create Storage Abstraction

1. Create `storage/base.py` with `StorageBackend` ABC
   - Define abstract methods matching current StateManager
   - Move `extract_video_id()` here (shared utility)
   - Move `YOUTUBE_PATTERNS` here

2. Create `storage/json.py` with `JSONStorage`
   - Copy current StateManager logic
   - Implement StorageBackend interface
   - Keep file locking and atomic writes

3. Create `storage/__init__.py`
   - Export `StorageBackend`, `get_storage()`
   - Factory reads `STORAGE_BACKEND` env var

### Phase 2: Implement SQLite Backend

4. Create `storage/sqlite.py` with `SQLiteStorage`
   - Create table on first access
   - Implement all StorageBackend methods
   - Use proper parameterized queries
   - Handle concurrent access (SQLite WAL mode)

### Phase 3: Integration

5. Update `state.py`
   - Become thin wrapper around `get_storage()`
   - Maintain backward-compatible API
   - Deprecation notice for direct StateManager use (optional)

6. Update `config.py`
   - Add `get_storage_backend()` helper
   - Add `get_storage_path()` helper

### Phase 4: Migration

7. Create `storage/migrate.py`
   - Function to migrate JSON → SQLite
   - Preserve all job data and timestamps

8. Add CLI support (optional)
   - `--migrate` flag to trigger migration
   - Auto-detect and prompt on first run with SQLite

## SQLite Schema

```sql
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
);

CREATE INDEX IF NOT EXISTS idx_jobs_stage ON jobs(stage);
CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at);
```

## Storage Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from transcripts.models import Job, Stage

class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        ...

    @abstractmethod
    def get_job_by_url(self, url: str) -> Optional[Job]:
        """Get a job by URL."""
        ...

    @abstractmethod
    def create_job(self, url: str) -> Job:
        """Create a new job or return existing one."""
        ...

    @abstractmethod
    def update_job(self, job: Job) -> None:
        """Update an existing job."""
        ...

    @abstractmethod
    def set_stage(self, job_id: str, stage: Stage, error: Optional[str] = None) -> Optional[Job]:
        """Update job stage."""
        ...

    @abstractmethod
    def list_jobs(self, filter_stage: Optional[Stage] = None) -> List[Job]:
        """List all jobs, optionally filtered by stage."""
        ...

    @abstractmethod
    def get_failed_jobs(self) -> List[Job]:
        """Get all failed jobs."""
        ...

    @abstractmethod
    def clear_jobs(self, filter_stage: Optional[Stage] = None) -> int:
        """Clear jobs from state."""
        ...

    @abstractmethod
    def verify_stage_files(self, job: Job) -> Stage:
        """Verify intermediate files exist and return adjusted stage."""
        ...
```

## Configuration

```bash
# Environment variables (add to .env)
STORAGE_BACKEND=sqlite    # "sqlite" (default) or "json"
STORAGE_PATH=             # Optional: custom path for storage file
                          # Defaults: .transcripts.db (sqlite) or .transcripts-state.json (json)
```

## Complexity Tracking

No complexity concerns - straightforward refactor with clear interface.

## Testing Checklist

- [ ] `transcribe <url>` works with SQLite (default)
- [ ] `transcribe --status` shows jobs from SQLite
- [ ] `transcribe --retry-failed` works with SQLite
- [ ] `transcribe --clear-completed` works with SQLite
- [ ] `transcribe --clear-all` works with SQLite
- [ ] `STORAGE_BACKEND=json transcribe <url>` uses JSON
- [ ] Migration from existing JSON to SQLite preserves all jobs
- [ ] Concurrent CLI calls don't corrupt data
