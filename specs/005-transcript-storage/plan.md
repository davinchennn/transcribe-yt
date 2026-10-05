# Implementation Plan: Transcript Storage

**Branch**: `005-transcript-storage` | **Date**: 2026-01-31 | **Spec**: [spec.md](./spec.md)

## Summary

Store full transcript content in SQLite database alongside job state. Enables retrieval without file access and full-text search across all transcripts. Files become optional export rather than primary storage.

## Technical Context

**Language/Version**: Python 3.8+
**Primary Dependencies**: Existing + sqlite3 FTS5 (built into SQLite)
**Storage**: SQLite (extends 004-storage-abstraction)
**Project Type**: Single project (monorepo core package)

## Project Structure

### Source Code Changes

```text
packages/core/src/transcripts/
├── storage/
│   ├── sqlite.py           # MODIFY: Add transcripts table + methods
│   ├── base.py             # MODIFY: Add transcript methods to ABC
│   └── json.py             # MODIFY: Add transcript methods (file-based fallback)
├── processor.py            # MODIFY: Save to database instead of files
├── models.py               # No changes (Transcript model exists)
└── cli/main.py             # MODIFY: Add --search flag
```

## Implementation Approach

### Phase 1: Database Schema

1. Add `transcripts` table to SQLite schema in `_init_db()`
2. Add FTS5 virtual table for full-text search
3. Add triggers to keep FTS index in sync

### Phase 2: Storage Methods

4. Add abstract methods to `StorageBackend` ABC:
   - `save_transcript(job_id, transcript)`
   - `get_transcript(job_id)`
   - `list_transcripts()`
   - `search_transcripts(query)`
   - `delete_transcript(job_id)`

5. Implement methods in `SQLiteStorage`:
   - Serialize words/utterances to JSON for storage
   - Deserialize back to Word/Utterance objects on retrieval
   - Use FTS5 for search queries

6. Implement methods in `JSONStorage` (file-based fallback):
   - Save/load transcript files as before
   - Search by loading and scanning files (slower but functional)

### Phase 3: Processor Integration

7. Update `TranscriptProcessor._save_transcript()`:
   - Save to database via storage backend
   - Optionally write files based on `output_format`
   - Update job record with transcript reference

8. Update processor to retrieve transcripts from database when needed

### Phase 4: CLI Integration

9. Add `--search` flag to CLI:
   - `transcribe --search "keyword"` searches all transcripts
   - Display matching results with context

10. Add `--export` flag for file export:
    - `transcribe --export <job_id> --format json`
    - Write transcript to file from database

### Phase 5: Migration

11. Add migration utility for existing file-based transcripts:
    - Scan `transcripts/` directory
    - Parse JSON files and insert into database
    - Match to existing jobs by title/URL

## Database Schema

```sql
-- Main transcripts table
CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    video_url TEXT NOT NULL,
    title TEXT,
    duration INTEGER,
    transcript_text TEXT NOT NULL,
    words TEXT,          -- JSON array
    utterances TEXT,     -- JSON array
    metadata TEXT,       -- JSON object
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_transcripts_job_id ON transcripts(job_id);

-- FTS5 full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    title,
    transcript_text,
    content='transcripts',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
    INSERT INTO transcripts_fts(rowid, title, transcript_text)
    VALUES (new.id, new.title, new.transcript_text);
END;

CREATE TRIGGER IF NOT EXISTS transcripts_ad AFTER DELETE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, title, transcript_text)
    VALUES('delete', old.id, old.title, old.transcript_text);
END;

CREATE TRIGGER IF NOT EXISTS transcripts_au AFTER UPDATE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, title, transcript_text)
    VALUES('delete', old.id, old.title, old.transcript_text);
    INSERT INTO transcripts_fts(rowid, title, transcript_text)
    VALUES (new.id, new.title, new.transcript_text);
END;
```

## Storage Interface Additions

```python
# Add to StorageBackend ABC

@abstractmethod
def save_transcript(self, job_id: str, transcript: Transcript) -> None:
    """Save transcript to storage."""
    ...

@abstractmethod
def get_transcript(self, job_id: str) -> Optional[Transcript]:
    """Get transcript by job ID."""
    ...

@abstractmethod
def list_transcripts(self) -> List[Transcript]:
    """List all transcripts."""
    ...

@abstractmethod
def search_transcripts(self, query: str) -> List[dict]:
    """Search transcripts by text content.

    Returns list of dicts with: job_id, title, snippet, rank
    """
    ...

@abstractmethod
def delete_transcript(self, job_id: str) -> bool:
    """Delete transcript by job ID."""
    ...
```

## Complexity Tracking

No significant complexity - straightforward extension of existing storage pattern.

## Testing Checklist

- [ ] New transcription saves to database
- [ ] `--status` still works (job data unaffected)
- [ ] Can retrieve transcript by job_id
- [ ] Search finds matching transcripts
- [ ] FTS ranking returns relevant results first
- [ ] `--export` writes correct file format
- [ ] Migration imports existing JSON files
- [ ] Deleting job cascades to delete transcript
- [ ] JSON backend works as fallback
