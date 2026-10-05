# Feature Specification: Web UI

**Feature Branch**: `007-web-ui`
**Depends On**: 004-storage-abstraction, 005-transcript-storage, 006-drop-utterances
**Created**: 2026-01-31
**Status**: Complete
**Input**: User description: "Build a web UI with FastAPI backend and React frontend for the transcripts application"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Job Dashboard (Priority: P1)

User opens the web application and sees a dashboard showing all transcription jobs with their current status, similar to the CLI `--status` output but in a rich visual format.

**Why this priority**: This is the entry point to the application. Without visibility into jobs, users can't effectively use any other feature.

**Independent Test**: Can be fully tested by loading the dashboard page and verifying jobs are displayed with correct status indicators.

**Acceptance Scenarios**:

1. **Given** the user has existing jobs, **When** they open the dashboard, **Then** they see a table/list of all jobs with title, status, provider, and timestamps
2. **Given** a job is in progress, **When** viewing the dashboard, **Then** the status shows with appropriate visual indicator (spinner/progress)
3. **Given** no jobs exist, **When** opening the dashboard, **Then** a helpful empty state is shown with guidance to submit a video

---

### User Story 2 - Submit New Transcription (Priority: P1)

User submits a YouTube URL through the web interface and sees real-time progress as it downloads and transcribes.

**Why this priority**: This is the core action of the application. Users need to be able to submit videos for transcription.

**Independent Test**: Can be tested by submitting a URL and observing the job appear in the dashboard with status updates.

**Acceptance Scenarios**:

1. **Given** the user is on the dashboard, **When** they enter a valid YouTube URL and click submit, **Then** a new job is created and appears in the job list
2. **Given** a job is submitted, **When** processing occurs, **Then** the UI updates to show current stage (downloading → extracting → transcribing → completed)
3. **Given** an invalid URL is entered, **When** submitting, **Then** a validation error is shown

---

### User Story 3 - View Transcript (Priority: P2)

User clicks on a completed job to view the full transcript with speaker labels and timestamps.

**Why this priority**: Viewing results is essential but depends on having completed jobs first.

**Independent Test**: Can be tested by clicking a completed job and verifying the transcript text displays correctly.

**Acceptance Scenarios**:

1. **Given** a completed job exists, **When** clicking on it, **Then** the full transcript is displayed with speaker labels
2. **Given** viewing a transcript, **When** the user wants to copy it, **Then** they can copy the text to clipboard
3. **Given** viewing a transcript, **When** the user clicks download, **Then** they can download as TXT or JSON

---

### User Story 4 - Retry Failed Jobs (Priority: P3)

User can retry a failed job with a single click from the dashboard.

**Why this priority**: Error recovery is important but less frequent than primary workflows.

**Independent Test**: Can be tested by clicking retry on a failed job and observing it restart processing.

**Acceptance Scenarios**:

1. **Given** a failed job exists, **When** clicking the retry button, **Then** the job resets to pending and starts processing
2. **Given** multiple failed jobs exist, **When** clicking "Retry All Failed", **Then** all failed jobs are queued for retry

---

### User Story 5 - Batch URL Submission (Priority: P3)

User can submit multiple YouTube URLs at once (paste multiple lines or upload a file).

**Why this priority**: Power user feature that builds on single URL submission.

**Independent Test**: Can be tested by pasting multiple URLs and verifying multiple jobs are created.

**Acceptance Scenarios**:

1. **Given** the user pastes multiple URLs (one per line), **When** submitting, **Then** a job is created for each URL
2. **Given** some URLs are invalid in a batch, **When** submitting, **Then** valid URLs are processed and invalid ones show errors

---

### Edge Cases

- What happens when the backend is unreachable? → Show connection error with retry option
- What happens when a very long video is submitted? → Show estimated time, allow cancellation
- What happens when the API key is missing/invalid? → Show configuration error with instructions
- How does system handle concurrent submissions? → Queue jobs, show queue position

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a REST API for all job operations (list, create, get, retry, delete)
- **FR-002**: System MUST serve a web frontend accessible via browser
- **FR-003**: System MUST display job status with visual indicators (colors, icons)
- **FR-004**: System MUST validate YouTube URLs before creating jobs
- **FR-005**: System MUST provide real-time or near-real-time status updates
- **FR-006**: System MUST allow viewing full transcript content for completed jobs
- **FR-007**: System MUST allow downloading transcripts in multiple formats (JSON, TXT)
- **FR-008**: System MUST allow retrying failed jobs
- **FR-009**: System MUST allow clearing job history (with confirmation)

### API Endpoints

- `GET /api/jobs` - List all jobs
- `POST /api/jobs` - Create new job(s) from URL(s)
- `GET /api/jobs/{id}` - Get job details including transcript
- `POST /api/jobs/{id}/retry` - Retry a failed job
- `DELETE /api/jobs/{id}` - Delete a job
- `DELETE /api/jobs` - Clear jobs (with filter param)
- `GET /api/health` - Health check endpoint

### Key Entities

- **Job**: Transcription task with id, url, stage, title, provider, timestamps, error, file paths
- **Transcript**: Result with video_url, title, text, words (with timing), utterances (speaker-labeled)

## Technical Approach

### Backend (packages/api/)

- **Framework**: FastAPI
- **Integration**: Imports and uses existing `transcripts` package directly
- **Background Tasks**: Use FastAPI BackgroundTasks for long-running transcription
- **State**: Uses StorageBackend abstraction (SQLite default, from 004-storage-abstraction)

### Frontend (packages/web/)

- **Framework**: React 18+ with TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **State Management**: TanStack Query for server state
- **Components**: shadcn/ui for UI primitives

### Development

- API runs on port 8000 (`uvicorn`)
- Frontend dev server on port 5173 (`vite`)
- Frontend proxies `/api` to backend in development

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can submit a URL and see status updates without refreshing the page
- **SC-002**: Dashboard loads and displays jobs in under 2 seconds
- **SC-003**: All CLI functionality is accessible through the web UI
- **SC-004**: System works in modern browsers (Chrome, Firefox, Safari, Edge)
