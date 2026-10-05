# Feature Specification: YouTube Transcripts

**Feature Branch**: `001-youtube-transcripts`
**Created**: 2026-01-25
**Status**: Implemented (Retroactive Documentation)
**Input**: Document the existing transcripts tool that downloads YouTube videos and generates transcripts using Deepgram or AssemblyAI

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Transcribe a Single Video (Priority: P1)

A user wants to quickly get a transcript from a YouTube video for note-taking, content repurposing, or accessibility purposes.

**Why this priority**: Core functionality - the most common use case for the tool.

**Independent Test**: Can be fully tested by running `transcribe "https://youtube.com/watch?v=VIDEO_ID"` and verifying transcript files are created.

**Acceptance Scenarios**:

1. **Given** a valid YouTube video URL, **When** the user runs `transcribe URL`, **Then** the system downloads the video, extracts audio, transcribes it, and saves JSON and TXT files to the transcripts directory.
2. **Given** a valid YouTube video URL and `--no-video` flag, **When** the user runs the command, **Then** only audio is downloaded (no video file retained).
3. **Given** a valid YouTube video URL and `--provider assemblyai` flag, **When** the user runs the command, **Then** AssemblyAI is used instead of the default Deepgram.

---

### User Story 2 - Transcribe a Playlist (Priority: P2)

A user wants to transcribe all videos in a YouTube playlist in one operation.

**Why this priority**: Batch efficiency for content creators or researchers working with video series.

**Independent Test**: Can be tested by running `transcribe --playlist PLAYLIST_URL` and verifying multiple transcript files are created.

**Acceptance Scenarios**:

1. **Given** a valid YouTube playlist URL, **When** the user runs `transcribe --playlist URL`, **Then** all videos in the playlist are downloaded and transcribed sequentially.
2. **Given** a playlist where one video fails, **When** processing continues, **Then** remaining videos are still transcribed and errors are logged.

---

### User Story 3 - Batch Processing from File (Priority: P2)

A user has a list of YouTube URLs in a text file and wants to transcribe them all.

**Why this priority**: Flexibility for users with curated video lists from various sources.

**Independent Test**: Can be tested by creating a file with URLs and running `transcribe --file urls.txt`.

**Acceptance Scenarios**:

1. **Given** a text file with one URL per line, **When** the user runs `transcribe --file urls.txt`, **Then** each URL is processed and transcribed.
2. **Given** a file with comment lines (starting with #), **When** processing, **Then** comment lines are ignored.

---

### User Story 4 - Python API Integration (Priority: P3)

A developer wants to integrate transcription into their own Python application.

**Why this priority**: Enables programmatic access for automation and custom workflows.

**Independent Test**: Can be tested by importing `TranscriptProcessor` and calling `process_video()`.

**Acceptance Scenarios**:

1. **Given** a Python script importing `TranscriptProcessor`, **When** calling `processor.process_video(url)`, **Then** a `Transcript` object is returned with all metadata and text.
2. **Given** a `Transcript` object, **When** accessing `.transcript_text`, `.words`, or `.utterances`, **Then** the relevant data is available.

---

### Edge Cases

- What happens when a video is private or age-restricted? System raises an error during download.
- What happens when API key is missing? System raises an error with guidance to configure `.env`.
- What happens when a file already exists with the same name? Timestamp is appended to filename.
- What happens when network connection fails mid-transcription? Error is raised and reported.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST download YouTube videos using yt-dlp
- **FR-002**: System MUST extract audio from video files using FFmpeg
- **FR-003**: System MUST transcribe audio using Deepgram (default) or AssemblyAI
- **FR-004**: System MUST support speaker diarization (identifying different speakers)
- **FR-005**: System MUST save transcripts in JSON format with full metadata
- **FR-006**: System MUST save transcripts in human-readable TXT format
- **FR-007**: System MUST support multiple text output formats: conversation, timestamped, markdown, simple, compact
- **FR-008**: System MUST provide word-level timestamps and confidence scores
- **FR-009**: System MUST provide utterance-level speaker segmentation
- **FR-010**: System MUST handle playlists by processing each video sequentially
- **FR-011**: System MUST handle batch processing from a file of URLs
- **FR-012**: System MUST allow configuration via environment variables or CLI arguments
- **FR-013**: System MUST provide a Python API via `TranscriptProcessor` class

### Key Entities

- **Transcript**: Complete transcription result containing video URL, title, duration, transcript text, words with timestamps, speaker-segmented utterances, and metadata
- **Word**: Individual word with text, start/end timestamps (milliseconds), confidence score, and optional speaker label
- **Utterance**: Continuous speech segment by one speaker with text, timestamps, and speaker label

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can transcribe a single YouTube video with one command
- **SC-002**: Users can transcribe entire playlists without manual intervention
- **SC-003**: Transcripts include accurate speaker separation when multiple speakers are present
- **SC-004**: Output files are human-readable and include video metadata (title, URL, duration)
- **SC-005**: System supports both Deepgram and AssemblyAI as transcription providers
- **SC-006**: Python developers can integrate transcription into their applications using the `TranscriptProcessor` class
- **SC-007**: System handles errors gracefully, continuing batch processing when individual videos fail

## Assumptions

- User has Python 3.8+ installed
- User has FFmpeg installed and available in PATH
- User has a valid API key for Deepgram or AssemblyAI
- YouTube videos are publicly accessible (not private or age-restricted)
- Network connectivity is available for downloading and API calls
