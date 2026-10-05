# Tasks: File Retention Options

**Input**: Design documents from `/specs/008-file-retention/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested - no test tasks included.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Core package**: `packages/core/src/transcripts/`
- **API package**: `packages/api/src/api/`
- **Storage**: `packages/core/src/transcripts/storage/`

---

## Phase 1: Setup (No Changes Required)

**Purpose**: Project already has existing structure - no setup needed

This feature extends an existing codebase. No new project setup required.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core model and storage changes that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T001 Add `keep_video` and `keep_audio` fields to Job model in packages/core/src/transcripts/models.py
- [x] T002 Update Job.to_dict() and Job.from_dict() to handle new fields in packages/core/src/transcripts/models.py
- [x] T003 [P] Add SQLite migration for new columns in packages/core/src/transcripts/storage/sqlite.py
- [x] T004 [P] Update JSON storage to handle new fields with defaults in packages/core/src/transcripts/storage/json.py

**Checkpoint**: Foundation ready - Job model now supports retention preferences

---

## Phase 3: User Story 1 - Default Transcription with Full Media Retention (Priority: P1) 🎯 MVP

**Goal**: System downloads full video first, extracts audio from it, and keeps both files by default

**Independent Test**: Transcribe any YouTube video with default settings, verify both video (.mp4) and audio (.mp3) files exist in downloads/videos/ and downloads/audio/

### Implementation for User Story 1

- [x] T005 [US1] Modify YouTubeDownloader.download_video() to always download full video first in packages/core/src/transcripts/downloader.py
- [x] T006 [US1] Add new method to extract audio from downloaded video using FFmpeg in packages/core/src/transcripts/downloader.py
- [x] T007 [US1] Update TranscriptProcessor.process_video() to use new download flow (video first, then extract) in packages/core/src/transcripts/processor.py
- [x] T008 [US1] Add retention options (keep_video, keep_audio) to TranscriptProcessor.__init__() in packages/core/src/transcripts/processor.py
- [x] T009 [US1] Pass retention preferences to StateManager.create_job() in packages/core/src/transcripts/processor.py
- [x] T010 [US1] Update StateManager.create_job() to accept and store retention preferences in packages/core/src/transcripts/state.py
- [x] T011 [P] [US1] Add --keep-video/--no-keep-video CLI arguments in packages/core/src/transcripts/cli/main.py
- [x] T012 [P] [US1] Add --keep-audio/--no-keep-audio CLI arguments in packages/core/src/transcripts/cli/main.py
- [x] T013 [US1] Pass CLI retention arguments to TranscriptProcessor in packages/core/src/transcripts/cli/main.py
- [x] T014 [P] [US1] Add keep_video and keep_audio fields to JobCreate schema in packages/api/src/api/schemas.py
- [x] T015 [US1] Pass API retention options to TranscriptProcessor in process_job() in packages/api/src/api/routes.py

**Checkpoint**: User Story 1 complete - default transcription downloads video, extracts audio, keeps both files

---

## Phase 4: User Story 2 - Transcription with Audio Only (Priority: P2)

**Goal**: When keep_video=false, video file is deleted after successful transcription

**Independent Test**: Transcribe with --no-keep-video, verify only audio file remains after completion

### Implementation for User Story 2

- [x] T016 [US2] Add _cleanup_files() method to TranscriptProcessor in packages/core/src/transcripts/processor.py
- [x] T017 [US2] Implement video file deletion logic in _cleanup_files() when keep_video=false in packages/core/src/transcripts/processor.py
- [x] T018 [US2] Call _cleanup_files() after successful transcription (Stage.COMPLETED) in packages/core/src/transcripts/processor.py
- [x] T019 [US2] Add logging for file deletion actions in packages/core/src/transcripts/processor.py

**Checkpoint**: User Story 2 complete - video can be deleted after transcription while keeping audio

---

## Phase 5: User Story 3 - Transcription with No Media Retention (Priority: P3)

**Goal**: When both keep_video=false and keep_audio=false, all media files are deleted after successful transcription

**Independent Test**: Transcribe with --no-keep-video --no-keep-audio, verify no media files remain (only transcript in database)

### Implementation for User Story 3

- [x] T020 [US3] Implement audio file deletion logic in _cleanup_files() when keep_audio=false in packages/core/src/transcripts/processor.py
- [x] T021 [US3] Ensure files are NOT deleted when transcription fails (Stage.FAILED) in packages/core/src/transcripts/processor.py

**Checkpoint**: User Story 3 complete - both files can be deleted, files retained on failure

---

## Phase 6: User Story 4 - Transcription with Video Only (Priority: P3)

**Goal**: When keep_audio=false (but keep_video=true), audio file is deleted while video is retained

**Independent Test**: Transcribe with --no-keep-audio, verify only video file remains

### Implementation for User Story 4

- [x] T022 [US4] Verify _cleanup_files() handles keep_audio=false independently from keep_video in packages/core/src/transcripts/processor.py

**Checkpoint**: User Story 4 complete - all four retention combinations work correctly

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Error handling, edge cases, and documentation

- [x] T023 [P] Handle file deletion failures gracefully (log warning, don't fail job) in packages/core/src/transcripts/processor.py
- [x] T024 [P] Update help text for CLI retention arguments in packages/core/src/transcripts/cli/main.py
- [x] T025 Run quickstart.md validation - test all four retention scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: No dependencies - starts immediately
- **User Story 1 (Phase 3)**: Depends on Foundational (T001-T004)
- **User Story 2 (Phase 4)**: Depends on User Story 1 (needs _cleanup_files scaffolding from T016)
- **User Story 3 (Phase 5)**: Depends on User Story 2 (extends _cleanup_files)
- **User Story 4 (Phase 6)**: Depends on User Story 3 (verification task only)
- **Polish (Phase 7)**: Depends on all user stories

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - establishes download/extract flow
- **User Story 2 (P2)**: Depends on US1 - adds video cleanup
- **User Story 3 (P3)**: Depends on US2 - adds audio cleanup + failure handling
- **User Story 4 (P3)**: Depends on US3 - verification only (same priority as US3)

### Within Each User Story

- Models before services
- Services before endpoints/CLI
- Core implementation before API integration

### Parallel Opportunities

**Foundational Phase:**
```bash
# T003 and T004 can run in parallel (different files):
Task: T003 - SQLite migration
Task: T004 - JSON storage update
```

**User Story 1:**
```bash
# CLI and API tasks can run in parallel after core implementation:
Task: T011 - --keep-video CLI arg
Task: T012 - --keep-audio CLI arg
Task: T014 - API schema update
```

**Polish Phase:**
```bash
# All polish tasks can run in parallel:
Task: T023 - Error handling
Task: T024 - Help text update
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (T001-T004)
2. Complete Phase 3: User Story 1 (T005-T015)
3. **STOP and VALIDATE**: Test default transcription - verify both files kept
4. Deploy/demo if ready

### Incremental Delivery

1. Complete Foundational → Model ready with retention fields
2. Add User Story 1 → Default behavior: download video, extract audio, keep both
3. Add User Story 2 → Video cleanup when keep_video=false
4. Add User Story 3 → Audio cleanup when keep_audio=false, failure handling
5. Add User Story 4 → Verify all combinations work
6. Polish → Error handling, documentation

### Sequential Approach (Recommended)

This feature has natural dependencies between user stories:
- US1 establishes the new download flow
- US2-US4 add cleanup variations

Execute in order: Foundational → US1 → US2 → US3 → US4 → Polish

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- No tests included (not explicitly requested in spec)
- US3 and US4 have same priority (P3) but US4 depends on US3
- Failure case (files retained) is handled in US3 (T021)
- Commit after each task or logical group
