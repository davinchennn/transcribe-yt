# Tasks: Progress Tracking

**Input**: Design documents from `/specs/002-progress-tracking/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Add new dependency and create core module structure

- [ ] T001 Add `filelock` dependency to pyproject.toml
- [ ] T002 Create src/transcripts/state.py with module docstring and imports

---

## Phase 2: Foundational (Core State Management)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T003 Add Stage enum to src/transcripts/models.py (pending, downloading, extracting, transcribing, saving, completed, failed)
- [ ] T004 Add Job dataclass to src/transcripts/models.py with fields: id, url, title, stage, error, video_file, audio_file, transcript_file, created_at, updated_at
- [ ] T005 Add Job.to_dict() and Job.from_dict() methods to src/transcripts/models.py
- [ ] T006 Implement StateManager class in src/transcripts/state.py with __init__(state_file_path)
- [ ] T007 Implement StateManager._load() and StateManager._save() with atomic writes in src/transcripts/state.py
- [ ] T008 Implement StateManager.get_job(video_id) in src/transcripts/state.py
- [ ] T009 Implement StateManager.create_job(url) with video ID extraction in src/transcripts/state.py
- [ ] T010 Implement StateManager.update_job(job) with file locking in src/transcripts/state.py
- [ ] T011 Add helper function extract_video_id(url) to src/transcripts/state.py

**Checkpoint**: Foundation ready - StateManager can create, read, update jobs

---

## Phase 3: User Story 1 - Resume Failed Transcription (Priority: P1) 🎯 MVP

**Goal**: Users can resume a failed job from its last successful stage without re-processing completed steps

**Independent Test**: Start transcription, kill mid-process, re-run same URL, verify it resumes from checkpoint

### Implementation for User Story 1

- [ ] T012 [US1] Add stage transition methods to StateManager: set_stage(job_id, stage) in src/transcripts/state.py
- [ ] T013 [US1] Add file verification method: verify_stage_files(job) returns adjusted stage in src/transcripts/state.py
- [ ] T014 [US1] Modify TranscriptProcessor.__init__() to accept optional StateManager in src/transcripts/processor.py
- [ ] T015 [US1] Modify TranscriptProcessor.process_video() to create/lookup job at start in src/transcripts/processor.py
- [ ] T016 [US1] Add stage transitions in process_video(): set downloading before download in src/transcripts/processor.py
- [ ] T017 [US1] Add stage transitions in process_video(): set extracting before extract in src/transcripts/processor.py
- [ ] T018 [US1] Add stage transitions in process_video(): set transcribing before API call in src/transcripts/processor.py
- [ ] T019 [US1] Add stage transitions in process_video(): set saving before file write in src/transcripts/processor.py
- [ ] T020 [US1] Add stage transitions in process_video(): set completed after success in src/transcripts/processor.py
- [ ] T021 [US1] Add error handling in process_video(): set failed with error message on exception in src/transcripts/processor.py
- [ ] T022 [US1] Implement resume logic: check existing job, verify files, skip completed stages in src/transcripts/processor.py
- [ ] T023 [US1] Update job with file paths (video_file, audio_file, transcript_file) after each stage in src/transcripts/processor.py
- [ ] T024 [US1] Initialize StateManager in CLI main() and pass to TranscriptProcessor in src/transcripts/cli/main.py

**Checkpoint**: Users can now resume failed transcriptions by re-running the same URL

---

## Phase 4: User Story 2 - View Job Status (Priority: P2)

**Goal**: Users can see status of all jobs with a single command

**Independent Test**: Run `transcribe list` and see list of jobs with their current state

### Implementation for User Story 2

- [ ] T025 [US2] Add StateManager.list_jobs(filter_stage=None) method in src/transcripts/state.py
- [ ] T026 [US2] Add list subcommand to argument parser in src/transcripts/cli/main.py
- [ ] T027 [US2] Implement status display: format job list as table (title, stage, error, updated_at) in src/transcripts/cli/main.py
- [ ] T028 [US2] Handle empty state file gracefully (show "No jobs found") in src/transcripts/cli/main.py

**Checkpoint**: Users can view all jobs and their status

---

## Phase 5: User Story 3 - Retry All Failed Jobs (Priority: P2)

**Goal**: Users can retry all failed jobs at once

**Independent Test**: Create multiple failed jobs, run `transcribe --retry-failed`, verify all resume

### Implementation for User Story 3

- [ ] T029 [US3] Add StateManager.get_failed_jobs() method in src/transcripts/state.py
- [ ] T030 [US3] Add --retry-failed flag to argument parser in src/transcripts/cli/main.py
- [ ] T031 [US3] Implement retry-failed: get failed jobs, process each with resume logic in src/transcripts/cli/main.py
- [ ] T032 [US3] Add progress output showing which job is being retried (X of N) in src/transcripts/cli/main.py

**Checkpoint**: Users can retry all failed jobs with one command

---

## Phase 6: User Story 4 - Clear Job History (Priority: P3)

**Goal**: Users can clear old job records

**Independent Test**: Run `transcribe --clear-completed`, verify completed jobs are removed from status

### Implementation for User Story 4

- [ ] T033 [US4] Add StateManager.clear_jobs(filter_stage=None) method in src/transcripts/state.py
- [ ] T034 [US4] Add --clear-completed flag to argument parser in src/transcripts/cli/main.py
- [ ] T035 [US4] Add --clear-all flag to argument parser in src/transcripts/cli/main.py
- [ ] T036 [US4] Implement clear-completed: remove only completed jobs in src/transcripts/cli/main.py
- [ ] T037 [US4] Implement clear-all: remove all jobs with confirmation prompt in src/transcripts/cli/main.py

**Checkpoint**: Users can manage job history

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements

- [ ] T038 [P] Add docstrings to all new public methods in src/transcripts/state.py
- [ ] T039 [P] Add docstrings to modified methods in src/transcripts/processor.py
- [ ] T040 Update README.md with new CLI flags documentation
- [ ] T041 Handle edge case: corrupted state file (log warning, recreate) in src/transcripts/state.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup
- **User Story 1 (Phase 3)**: Depends on Foundational - **MVP**
- **User Story 2 (Phase 4)**: Depends on Foundational (can run parallel to US1)
- **User Story 3 (Phase 5)**: Depends on US1 (uses resume logic)
- **User Story 4 (Phase 6)**: Depends on Foundational (can run parallel to US1)
- **Polish (Phase 7)**: After all user stories

### User Story Dependencies

```
         ┌─────────────────┐
         │   Foundational  │
         └────────┬────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
  [US1]         [US2]         [US4]
  Resume        Status        Clear
    │
    ▼
  [US3]
  Retry All
```

### Parallel Opportunities

**Within Foundational (T003-T011)**:
- T003, T004 can run in parallel (different parts of models.py, but recommend sequential for cleaner diffs)

**User Stories after Foundational**:
- US1, US2, US4 can start in parallel
- US3 must wait for US1

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T011)
3. Complete Phase 3: User Story 1 (T012-T024)
4. **STOP and VALIDATE**: Test resume functionality
5. Deploy if ready - users can already resume failed jobs

### Incremental Delivery

1. MVP: Setup + Foundational + US1 → Resume works
2. Add US2 → Users can check status
3. Add US3 → Users can retry all at once
4. Add US4 → Users can clean up history
5. Polish → Documentation, edge cases

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| Setup | 2 | Add dependency, create module |
| Foundational | 9 | StateManager, Job model |
| US1 (P1) | 13 | Resume failed - **MVP** |
| US2 (P2) | 4 | View status |
| US3 (P2) | 4 | Retry all failed |
| US4 (P3) | 5 | Clear history |
| Polish | 4 | Docs, edge cases |
| **Total** | **41** | |
