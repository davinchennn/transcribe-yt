# Tasks: Storage Abstraction

**Input**: Design documents from `/specs/004-storage-abstraction/`
**Prerequisites**: plan.md, spec.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Create storage package structure

- [ ] T001 Create `packages/core/src/transcripts/storage/` directory
- [ ] T002 [P] Create `storage/__init__.py` with placeholder exports

**Checkpoint**: Package structure ready

---

## Phase 2: Foundational (Abstract Interface)

**Purpose**: Define the storage interface that all backends implement

- [ ] T003 Create `storage/base.py` with `StorageBackend` ABC defining all abstract methods
- [ ] T004 Move `extract_video_id()` and `YOUTUBE_PATTERNS` from `state.py` to `storage/base.py`
- [ ] T005 Update `storage/__init__.py` to export `StorageBackend`

**Checkpoint**: Abstract interface defined, ready for implementations

---

## Phase 3: User Story 1 - SQLite Default Storage (Priority: P1)

**Goal**: SQLite backend works as the default storage

**Independent Test**: Run `transcribe <url>` and verify `.transcripts.db` is created with job data

### Implementation

- [ ] T006 [US1] Create `storage/sqlite.py` with `SQLiteStorage` class skeleton implementing `StorageBackend`
- [ ] T007 [US1] Implement `_init_db()` method to create schema (jobs table + indexes)
- [ ] T008 [US1] Implement `create_job()` method with INSERT or SELECT existing
- [ ] T009 [US1] Implement `get_job()` and `get_job_by_url()` methods
- [ ] T010 [US1] Implement `update_job()` method
- [ ] T011 [US1] Implement `set_stage()` method
- [ ] T012 [US1] Implement `list_jobs()` method with optional stage filter
- [ ] T013 [US1] Implement `get_failed_jobs()` method
- [ ] T014 [US1] Implement `clear_jobs()` method with optional stage filter
- [ ] T015 [US1] Implement `verify_stage_files()` method (can reuse logic from state.py)
- [ ] T016 [US1] Enable WAL mode for better concurrent read performance
- [ ] T017 [US1] Add `get_storage()` factory function to `storage/__init__.py` (returns SQLite by default)
- [ ] T018 [US1] Update `config.py` with `get_storage_backend()` and `get_storage_path()` helpers
- [ ] T019 [US1] Update `state.py` to use `get_storage()` internally (maintain backward compat)
- [ ] T020 [US1] Test: Run `transcribe <url>` and verify SQLite storage works

**Checkpoint**: SQLite backend fully functional as default

---

## Phase 4: User Story 2 - JSON Backend Preserved (Priority: P2)

**Goal**: JSON storage still works when configured via environment variable

**Independent Test**: Run `STORAGE_BACKEND=json transcribe <url>` and verify `.transcripts-state.json` is used

### Implementation

- [ ] T021 [P] [US2] Create `storage/json.py` with `JSONStorage` class skeleton implementing `StorageBackend`
- [ ] T022 [US2] Move JSON load/save logic from `state.py` to `JSONStorage`
- [ ] T023 [US2] Move file locking logic to `JSONStorage`
- [ ] T024 [US2] Implement all `StorageBackend` methods in `JSONStorage` (refactor from state.py)
- [ ] T025 [US2] Update `get_storage()` factory to support `STORAGE_BACKEND=json`
- [ ] T026 [US2] Test: Run with `STORAGE_BACKEND=json` and verify JSON file is used

**Checkpoint**: Both backends work, selectable via environment variable

---

## Phase 5: User Story 3 - Data Migration (Priority: P2)

**Goal**: Users can migrate existing JSON data to SQLite

**Independent Test**: Have existing `.transcripts-state.json`, run migration, verify all jobs in SQLite

### Implementation

- [ ] T027 [US3] Create `storage/migrate.py` with `migrate_json_to_sqlite()` function
- [ ] T028 [US3] Implement: Read all jobs from JSON file
- [ ] T029 [US3] Implement: Insert all jobs into SQLite database
- [ ] T030 [US3] Implement: Optional backup of JSON file after migration
- [ ] T031 [US3] Add `--migrate` flag to CLI in `cli/main.py`
- [ ] T032 [US3] Test: Create JSON state, run migration, verify data in SQLite

**Checkpoint**: Migration path complete

---

## Phase 6: Polish

**Purpose**: Cleanup and final integration

- [ ] T033 Remove duplicate code from `state.py` (now delegating to storage)
- [ ] T034 Update `.gitignore` to include `.transcripts.db`
- [ ] T035 Update `CLAUDE.md` with storage configuration info
- [ ] T036 Final test: Full CLI workflow with SQLite (submit, status, retry, clear)

---

## Dependencies & Execution Order

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational - ABC)
    ↓
Phase 3 (US1 - SQLite) ←── MVP: Stop here for minimum viable
    ↓
Phase 4 (US2 - JSON) ←── Can run parallel with Phase 5
    ↓
Phase 5 (US3 - Migration)
    ↓
Phase 6 (Polish)
```

### Parallel Opportunities

- T001, T002 can run in parallel
- T021 (JSON skeleton) can start parallel with Phase 3 SQLite work
- Phase 4 and Phase 5 can run in parallel after Phase 3

---

## Task Count Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 2 | Setup |
| 2 | 3 | Foundational (ABC) |
| 3 | 15 | US1 - SQLite |
| 4 | 6 | US2 - JSON |
| 5 | 6 | US3 - Migration |
| 6 | 4 | Polish |
| **Total** | **36** | |
