# Feature Specification: File Retention Options

**Feature Branch**: `008-file-retention`
**Created**: 2026-02-02
**Status**: Draft
**Input**: User description: "File retention options for transcription: Add options to control whether video and audio files are retained after transcription. Options: keep_video (default: true), keep_audio (default: true). Change default behavior to always download full video first, then extract audio from it. If keep_video=false, delete video after transcription. If keep_audio=false, delete audio after transcription. Both files kept by default."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Default Transcription with Full Media Retention (Priority: P1)

A user wants to transcribe a YouTube video and keep both the video and audio files for future reference, editing, or archival purposes. The system downloads the full video, extracts audio for transcription, completes the transcription, and retains both files.

**Why this priority**: This is the primary use case and the new default behavior. Most users want to keep their media files after transcription for rewatching, clipping, or archival.

**Independent Test**: Can be fully tested by transcribing any YouTube video with default settings and verifying both video and audio files exist after completion.

**Acceptance Scenarios**:

1. **Given** a user initiates transcription with default settings, **When** transcription completes successfully, **Then** both video file and audio file are retained in their respective directories
2. **Given** a user initiates transcription with default settings, **When** transcription completes, **Then** the video file is in the `downloads/videos/` directory and audio file is in `downloads/audio/` directory
3. **Given** a user initiates transcription with default settings, **When** the system processes the video, **Then** the video is downloaded first, then audio is extracted from it (not downloaded separately)

---

### User Story 2 - Transcription with Audio Only (Priority: P2)

A user wants to transcribe a video but only needs the audio file (e.g., for podcast extraction or audio-only archival). They set `keep_video=false` to automatically clean up the video file after transcription while retaining the audio.

**Why this priority**: Common use case for users who want transcripts plus audio but don't need to store large video files.

**Independent Test**: Can be tested by transcribing a video with `keep_video=false` and verifying only the audio file remains after completion.

**Acceptance Scenarios**:

1. **Given** a user sets `keep_video=false`, **When** transcription completes successfully, **Then** the video file is deleted and only the audio file remains
2. **Given** a user sets `keep_video=false`, **When** transcription fails, **Then** all downloaded files are retained for debugging/retry purposes

---

### User Story 3 - Transcription with No Media Retention (Priority: P3)

A user only needs the transcript text and wants to minimize disk space usage. They set both `keep_video=false` and `keep_audio=false` to clean up all media files after successful transcription.

**Why this priority**: Useful for users focused purely on transcripts who want to conserve storage space.

**Independent Test**: Can be tested by transcribing a video with both retention options set to false and verifying no media files remain after completion.

**Acceptance Scenarios**:

1. **Given** a user sets `keep_video=false` and `keep_audio=false`, **When** transcription completes successfully, **Then** both video and audio files are deleted
2. **Given** a user sets both options to false, **When** transcription completes, **Then** only the transcript (database record and/or output files) remains
3. **Given** a user sets both options to false, **When** transcription fails, **Then** files are retained for retry purposes

---

### User Story 4 - Transcription with Video Only (Priority: P3)

A user wants to keep the video file but delete the extracted audio (since audio can be re-extracted from video if needed). They set `keep_audio=false` while keeping the default `keep_video=true`.

**Why this priority**: Less common use case but valid for users who want to minimize redundant storage.

**Independent Test**: Can be tested by transcribing with `keep_audio=false` and verifying only the video file remains.

**Acceptance Scenarios**:

1. **Given** a user sets `keep_audio=false` with default `keep_video=true`, **When** transcription completes successfully, **Then** the audio file is deleted and only the video file remains

---

### Edge Cases

- What happens when transcription fails? Files are retained regardless of retention settings to allow debugging and retry.
- What happens when disk space is insufficient during download? System reports error and cleans up partial downloads.
- What happens if file deletion fails (permissions, file locked)? System logs warning but does not fail the overall transcription job.
- What happens with existing jobs that have files? Retention settings only apply to new transcriptions, not retroactively.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST download the full video file before extracting audio (changed from current audio-only download)
- **FR-002**: System MUST provide a `keep_video` option that defaults to `true`
- **FR-003**: System MUST provide a `keep_audio` option that defaults to `true`
- **FR-004**: System MUST delete the video file after successful transcription when `keep_video=false`
- **FR-005**: System MUST delete the audio file after successful transcription when `keep_audio=false`
- **FR-006**: System MUST retain all files when transcription fails, regardless of retention settings
- **FR-007**: System MUST expose retention options via CLI arguments (`--keep-video`, `--keep-audio` or `--no-keep-video`, `--no-keep-audio`)
- **FR-008**: System MUST expose retention options via API request parameters
- **FR-009**: System MUST log file cleanup actions for debugging purposes
- **FR-010**: System MUST handle file deletion failures gracefully (log warning, do not fail job)

### Key Entities

- **Job**: Extended with retention preference fields (`keep_video`, `keep_audio`) to track user preferences per job
- **TranscriptProcessor**: Extended to handle file cleanup based on retention settings after successful transcription
- **Downloader**: Modified to always download full video first, then extract audio

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can configure file retention options for each transcription job
- **SC-002**: Default transcription behavior downloads and retains both video and audio files
- **SC-003**: File cleanup occurs automatically after successful transcription based on user preferences
- **SC-004**: Failed transcriptions retain all files 100% of the time for retry purposes
- **SC-005**: File deletion failures do not cause transcription jobs to fail

## Assumptions

- Users have sufficient disk space to temporarily store both video and audio during processing (even if retention is disabled)
- The existing `downloads/videos/` and `downloads/audio/` directory structure is retained
- Retention settings are per-job, not global application settings
- Existing transcription jobs are not affected by this feature (no retroactive cleanup)
