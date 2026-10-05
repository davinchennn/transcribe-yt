# Feature Specification: Transcript Storage

**Feature Branch**: `005-transcript-storage`
**Depends On**: 004-storage-abstraction
**Created**: 2026-01-31
**Status**: Draft
**Input**: User description: "Store all transcript content in SQLite database"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Store Transcripts in Database (Priority: P1)

When a transcription completes, the full transcript content (text, words with timing, speaker utterances) is stored in the SQLite database instead of only writing to files.

**Why this priority**: Core functionality - all other features depend on transcripts being in the database.

**Independent Test**: Run a transcription and verify the transcript data exists in the `transcripts` table.

**Acceptance Scenarios**:

1. **Given** a transcription completes, **When** checking the database, **Then** the full transcript text, words, and utterances are stored
2. **Given** a transcript is stored, **When** querying by job_id, **Then** all transcript data can be retrieved
3. **Given** word-level timing data exists, **When** stored, **Then** timestamps and confidence scores are preserved

---

### User Story 2 - Retrieve Transcripts from Database (Priority: P1)

Users and the system can retrieve full transcript content from the database without needing file access.

**Why this priority**: Essential for the web UI to display transcripts.

**Independent Test**: Query a stored transcript and verify all fields are returned correctly.

**Acceptance Scenarios**:

1. **Given** a transcript exists in the database, **When** retrieved by job_id, **Then** a complete Transcript object is returned
2. **Given** multiple transcripts exist, **When** listing transcripts, **Then** all are returned with metadata

---

### User Story 3 - Search Transcripts (Priority: P2)

Users can search across all transcript text to find specific content.

**Why this priority**: Key value-add of database storage - enables the "transcript search" feature from PROPOSALS.md.

**Independent Test**: Search for a word that appears in one transcript and verify it's found.

**Acceptance Scenarios**:

1. **Given** transcripts exist, **When** searching for a keyword, **Then** matching transcripts are returned with context
2. **Given** a search term appears multiple times, **When** searching, **Then** all occurrences are found

---

### User Story 4 - Optional File Export (Priority: P3)

Users can optionally export transcripts to JSON/TXT files for sharing or backup.

**Why this priority**: Nice-to-have for users who want file-based workflow.

**Independent Test**: Export a transcript and verify the file matches the database content.

**Acceptance Scenarios**:

1. **Given** a transcript in the database, **When** exporting to JSON, **Then** a valid JSON file is created
2. **Given** a transcript in the database, **When** exporting to TXT, **Then** a formatted text file is created

---

### Edge Cases

- What happens if transcript is very large (3+ MB)? → SQLite handles it fine, may add compression later
- What happens to existing file-based transcripts? → Migration utility to import them
- What happens if database storage fails? → Fall back to file storage, log warning

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST store transcript text, words, and utterances in SQLite
- **FR-002**: System MUST link transcripts to jobs via job_id foreign key
- **FR-003**: System MUST support full-text search on transcript content
- **FR-004**: System MUST preserve word-level timing (start, end, confidence)
- **FR-005**: System MUST preserve speaker labels in utterances
- **FR-006**: System MUST provide export to JSON and TXT formats
- **FR-007**: System SHOULD provide migration for existing file-based transcripts

### Database Schema

```sql
CREATE TABLE transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    video_url TEXT NOT NULL,
    title TEXT,
    duration INTEGER,              -- Duration in seconds
    transcript_text TEXT NOT NULL, -- Full plain text (searchable)
    words TEXT,                    -- JSON array of word objects
    utterances TEXT,               -- JSON array of utterance objects
    metadata TEXT,                 -- JSON object for extra data
    created_at TEXT NOT NULL
);

CREATE INDEX idx_transcripts_job_id ON transcripts(job_id);
CREATE VIRTUAL TABLE transcripts_fts USING fts5(
    transcript_text,
    content='transcripts',
    content_rowid='id'
);
```

### Key Entities

- **Transcript**: Full transcript with text, words (timing), utterances (speakers), metadata
- **Word**: Text, start_ms, end_ms, confidence, speaker
- **Utterance**: Speaker label, text, start_ms, end_ms

## Technical Approach

### Storage Methods

Add to `SQLiteStorage` class:
- `save_transcript(job_id: str, transcript: Transcript) -> None`
- `get_transcript(job_id: str) -> Optional[Transcript]`
- `search_transcripts(query: str) -> List[TranscriptSearchResult]`
- `export_transcript(job_id: str, format: str, path: str) -> str`

### Processor Integration

Update `TranscriptProcessor._save_transcript()`:
- Always save to database
- Optionally write files based on `output_format` setting

### Migration

Add `migrate_files_to_db()` function:
- Scan `transcripts/` directory for JSON files
- Parse and insert into database
- Link to existing jobs where possible

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All new transcripts are stored in SQLite automatically
- **SC-002**: Transcripts can be retrieved without file system access
- **SC-003**: Full-text search returns results in under 1 second for 1000 transcripts
- **SC-004**: Existing file-based transcripts can be migrated to database
