# Feature Specification: Progress Tracking

**Feature Branch**: `002-progress-tracking`
**Created**: 2026-01-25
**Status**: Draft
**Input**: Track transcription progress and resume failed jobs

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resume Failed Transcription (Priority: P1)

A user starts transcribing a video but the process fails partway through (network error, API timeout, system crash). They want to resume from where it stopped without re-downloading or re-processing completed steps.

**Why this priority**: Core value proposition - prevents wasted time and API costs when failures occur.

**Independent Test**: Can be tested by starting a transcription, simulating a failure mid-process, then running a resume command and verifying it continues from the last checkpoint.

**Acceptance Scenarios**:

1. **Given** a video that was downloaded but failed during transcription, **When** the user runs the resume command, **Then** the system skips the download step and retries transcription.
2. **Given** a video that failed during download, **When** the user runs the resume command, **Then** the system retries the download from the beginning.
3. **Given** a completed transcription job, **When** the user runs the resume command, **Then** the system reports "already completed" and does nothing.

---

### User Story 2 - View Job Status (Priority: P2)

A user wants to see the status of all transcription jobs - which are pending, in progress, completed, or failed.

**Why this priority**: Provides visibility into batch operations and helps users identify what needs attention.

**Independent Test**: Can be tested by running several transcriptions, then using a status command to list all jobs with their current state.

**Acceptance Scenarios**:

1. **Given** multiple jobs in various states, **When** the user runs the status command, **Then** they see a list of all jobs with their current status (pending, downloading, transcribing, completed, failed).
2. **Given** a failed job, **When** viewing status, **Then** the user sees the error message and which stage failed.

---

### User Story 3 - Retry All Failed Jobs (Priority: P2)

A user has multiple failed jobs and wants to retry them all at once rather than one by one.

**Why this priority**: Convenience for batch operations where multiple failures occurred.

**Independent Test**: Can be tested by creating several failed jobs, running retry-all, and verifying each resumes appropriately.

**Acceptance Scenarios**:

1. **Given** 3 failed jobs, **When** the user runs `transcribe --retry-failed`, **Then** all 3 jobs are retried from their last checkpoint.
2. **Given** no failed jobs, **When** the user runs `transcribe --retry-failed`, **Then** the system reports "no failed jobs to retry".

---

### User Story 4 - Clear Job History (Priority: P3)

A user wants to clear old job records to keep the status list manageable.

**Why this priority**: Housekeeping feature for long-term use.

**Independent Test**: Can be tested by creating jobs, clearing completed ones, and verifying they no longer appear in status.

**Acceptance Scenarios**:

1. **Given** completed and failed jobs, **When** the user runs `transcribe --clear-completed`, **Then** only completed jobs are removed from history.
2. **Given** jobs in history, **When** the user runs `transcribe --clear-all`, **Then** all job records are removed.

---

### Edge Cases

- What happens if the state file is corrupted? System recreates it and logs a warning.
- What happens if a video URL is no longer available when resuming? System marks job as failed with appropriate error.
- What happens if downloaded files were deleted but job shows "downloaded"? System detects missing files and restarts from download stage.
- What happens during concurrent runs? System uses file locking to prevent conflicts.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST persist job state to disk after each processing stage
- **FR-002**: System MUST track the following stages: pending, downloading, extracting, transcribing, saving, completed, failed
- **FR-003**: System MUST store the error message when a job fails
- **FR-004**: System MUST provide a command to view status of all jobs
- **FR-005**: System MUST provide a command to resume a specific failed job
- **FR-006**: System MUST provide a command to retry all failed jobs
- **FR-007**: System MUST automatically detect and resume interrupted jobs when re-running the same URL
- **FR-008**: System MUST verify that intermediate files exist before skipping stages
- **FR-009**: System MUST provide a command to clear job history
- **FR-010**: System MUST handle concurrent access to the state file safely

### Key Entities

- **Job**: A transcription task with a unique ID, video URL, current stage, status (pending/in_progress/completed/failed), error message if failed, timestamps for created/updated, and paths to intermediate files
- **Stage**: A step in the pipeline (pending → downloading → extracting → transcribing → saving → completed)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can resume a failed job without re-processing completed stages
- **SC-002**: Users can view the status of all jobs with a single command
- **SC-003**: Failed jobs retain enough information to resume from the correct stage
- **SC-004**: Intermediate files (video, audio) are reused when resuming
- **SC-005**: System prevents duplicate processing when the same URL is submitted twice

## Assumptions

- State is stored locally in the project directory (not in a database)
- Job history is scoped to the current project/directory
- Users run commands sequentially (concurrent batch processing is out of scope for v1)
