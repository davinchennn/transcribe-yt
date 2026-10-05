# Tasks: Transcript Storage

**Input**: Design documents from `/specs/005-transcript-storage/`
**Prerequisites**: plan.md, spec.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)

---

## Phase 1: Database Schema

**Purpose**: Add transcripts table and FTS5 search index

- [ ] T001 [US1] Add `transcripts` table schema to `SQLiteStorage._init_db()`
- [ ] T002 [US1] Add FTS5 virtual table `transcripts_fts` for full-text search
- [ ] T003 [US1] Add triggers to keep FTS index in sync (INSERT, UPDATE, DELETE)

**Checkpoint**: Schema ready for transcript storage

---

## Phase 2: Storage Methods (US1 + US2)

**Purpose**: Implement transcript CRUD operations

- [ ] T004 [US1] Implement `SQLiteStorage.save_transcript()` - serialize words/utterances to JSON
- [ ] T005 [US2] Implement `SQLiteStorage.get_transcript()` - deserialize JSON back to objects
- [ ] T006 [US2] Implement `SQLiteStorage.list_transcripts()` - return all with metadata
- [ ] T007 [US1] Implement `SQLiteStorage.delete_transcript()` - cascade handled by FK

**Checkpoint**: Can save and retrieve transcripts from SQLite

---

## Phase 3: Search (US3)

**Purpose**: Enable full-text search across transcripts

- [ ] T009 [US3] Add `search_transcripts(query)` method to `SQLiteStorage`
- [ ] T010 [US3] Implement FTS5 MATCH query with ranking
- [ ] T011 [US3] Return results with: job_id, title, snippet (with highlights), rank

**Checkpoint**: Search returns matching transcripts with context

---

## Phase 4: Processor Integration (US1)

**Purpose**: Save transcripts to database automatically

- [ ] T012 [US1] Update `TranscriptProcessor._save_transcript()` to call `storage.save_transcript()`
- [ ] T013 [US1] Make file output optional based on `output_format` setting
- [ ] T014 [US1] Test: Run transcription, verify data in database

**Checkpoint**: New transcriptions automatically saved to database

---

## Phase 5: CLI Integration (US3 + US4)

**Purpose**: Add search and export CLI commands

### Search

- [ ] T015 [US3] Add `--search` argument to CLI argparser
- [ ] T016 [US3] Implement `_search_transcripts()` function in CLI
- [ ] T017 [US3] Display results with title, snippet, and job_id

### Export

- [ ] T018 [P] [US4] Add `--export` argument with `--format` option (json/txt)
- [ ] T019 [P] [US4] Implement `_export_transcript()` function in CLI
- [ ] T020 [P] [US4] Write transcript to file in requested format

**Checkpoint**: Users can search and export via CLI

---

## Phase 6: Polish

**Purpose**: Final integration and documentation

- [ ] T021 Update `CLAUDE.md` with transcript storage info
- [ ] T022 Test: Full workflow - transcribe, search, export

---

## Dependencies & Execution Order

```
Phase 1 (Schema)
    ↓
Phase 2 (Storage Methods) ←── US1 + US2 complete
    ↓
Phase 3 (Search) ←── US3 complete
    ↓
Phase 4 (Processor) ←── Transcripts auto-saved
    ↓
Phase 5 (CLI) ←── US3 + US4 CLI access
    ↓
Phase 6 (Polish)
```

### Parallel Opportunities

- T018-T020 (Export CLI) can run parallel with T015-T017 (Search CLI)

---

## Task Count Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 3 | Database Schema |
| 2 | 4 | Storage Methods |
| 3 | 3 | Search |
| 4 | 3 | Processor Integration |
| 5 | 6 | CLI Integration |
| 6 | 2 | Polish |
| **Total** | **22** | |
