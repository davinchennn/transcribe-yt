# Feature Specification: Storage Abstraction

**Feature Branch**: `004-storage-abstraction`
**Created**: 2026-01-31
**Status**: Draft
**Input**: User description: "Abstract storage layer with JSON and SQLite backends, SQLite as default"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - SQLite Default Storage (Priority: P1)

Application uses SQLite by default for storing job state, providing better concurrency support and query capabilities for the upcoming web UI.

**Why this priority**: SQLite is the target storage for web UI concurrency requirements. This is the primary deliverable.

**Independent Test**: Can be tested by running the CLI with default settings and verifying jobs are stored in SQLite database file.

**Acceptance Scenarios**:

1. **Given** default configuration, **When** user runs a transcription, **Then** job state is stored in `.transcripts.db` SQLite file
2. **Given** SQLite storage, **When** multiple jobs exist, **Then** they can be queried and listed correctly
3. **Given** existing SQLite data, **When** application restarts, **Then** all job data persists correctly

---

### User Story 2 - JSON Backend Preserved (Priority: P2)

Users can opt to use the original JSON file storage via environment variable for simplicity or backward compatibility.

**Why this priority**: Maintains backward compatibility and provides a simpler option for testing or single-user scenarios.

**Independent Test**: Can be tested by setting `STORAGE_BACKEND=json` and verifying jobs are stored in JSON file.

**Acceptance Scenarios**:

1. **Given** `STORAGE_BACKEND=json` is set, **When** user runs a transcription, **Then** job state is stored in `.transcripts-state.json`
2. **Given** JSON storage, **When** application runs, **Then** behavior is identical to current implementation

---

### User Story 3 - Data Migration (Priority: P2)

Users with existing JSON data can migrate to SQLite seamlessly.

**Why this priority**: Ensures existing users don't lose their job history when upgrading.

**Independent Test**: Can be tested by having a JSON state file, running migration, and verifying all jobs appear in SQLite.

**Acceptance Scenarios**:

1. **Given** existing `.transcripts-state.json` file, **When** user runs with SQLite backend, **Then** they are prompted to migrate or migration happens automatically
2. **Given** migration completes, **When** viewing status, **Then** all historical jobs are preserved with correct data

---

### Edge Cases

- What happens if both SQLite and JSON files exist? → Use configured backend, warn about other file
- What happens if SQLite file is corrupted? → Show clear error, suggest backup restoration
- What happens during concurrent writes? → SQLite handles this; JSON uses file locking

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define a `StorageBackend` abstract interface for all storage operations
- **FR-002**: System MUST implement `SQLiteStorage` backend as the default
- **FR-003**: System MUST implement `JSONStorage` backend for backward compatibility
- **FR-004**: System MUST allow backend selection via `STORAGE_BACKEND` environment variable
- **FR-005**: System MUST provide a migration path from JSON to SQLite
- **FR-006**: System MUST maintain full API compatibility with existing `StateManager` usage
- **FR-007**: SQLite backend MUST handle concurrent access properly

### Storage Interface

```python
class StorageBackend(ABC):
    @abstractmethod
    def create_job(self, url: str) -> Job: ...

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]: ...

    @abstractmethod
    def update_job(self, job: Job) -> None: ...

    @abstractmethod
    def list_jobs(self, filter_stage: Optional[Stage] = None) -> List[Job]: ...

    @abstractmethod
    def delete_job(self, job_id: str) -> bool: ...

    @abstractmethod
    def clear_jobs(self, filter_stage: Optional[Stage] = None) -> int: ...
```

### Key Entities

- **StorageBackend**: Abstract interface defining all storage operations
- **SQLiteStorage**: SQLite implementation with `.transcripts.db` file
- **JSONStorage**: JSON file implementation (refactored from current StateManager)
- **Job**: Unchanged from current model

### SQLite Schema

```sql
CREATE TABLE jobs (
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

CREATE INDEX idx_jobs_stage ON jobs(stage);
CREATE INDEX idx_jobs_updated ON jobs(updated_at);
```

## Technical Approach

### File Structure

```
packages/core/src/transcripts/
├── storage/
│   ├── __init__.py      # Exports StorageBackend, get_storage()
│   ├── base.py          # StorageBackend ABC
│   ├── sqlite.py        # SQLiteStorage implementation
│   ├── json.py          # JSONStorage implementation
│   └── migrate.py       # JSON → SQLite migration
├── state.py             # Refactor to use StorageBackend
└── ...
```

### Migration Strategy

1. Refactor `StateManager` to use `StorageBackend` interface
2. Move current JSON logic to `JSONStorage` class
3. Implement `SQLiteStorage` class
4. Add `get_storage()` factory function
5. Add migration utility for JSON → SQLite
6. Update default to SQLite

### Configuration

```bash
# Environment variables
STORAGE_BACKEND=sqlite  # default, or "json"
STORAGE_PATH=.transcripts.db  # optional custom path
```

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing CLI commands work identically with SQLite backend
- **SC-002**: All existing tests pass with both backends
- **SC-003**: SQLite handles concurrent access without data corruption
- **SC-004**: Migration preserves 100% of job data from JSON to SQLite
- **SC-005**: Switching backends via environment variable works without code changes
