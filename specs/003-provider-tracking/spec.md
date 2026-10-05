# Feature Specification: Provider Tracking

**Feature Branch**: `003-provider-tracking`
**Created**: 2026-01-29
**Status**: Draft
**Input**: Track which transcription provider (Deepgram or AssemblyAI) was used for each job

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Provider in Job Status (Priority: P1)

A user wants to see which transcription provider was used for each job when viewing job status, so they can track costs and compare results across providers.

**Why this priority**: Core visibility - users need to know which service processed their transcripts.

**Independent Test**: Run `transcribe --status` and verify the provider column shows "deepgram" or "assemblyai" for each job.

**Acceptance Scenarios**:

1. **Given** a job transcribed with Deepgram, **When** viewing `--status`, **Then** the provider column shows "deepgram".
2. **Given** a job transcribed with AssemblyAI, **When** viewing `--status`, **Then** the provider column shows "assemblyai".
3. **Given** an existing job without provider info (legacy), **When** viewing `--status`, **Then** the provider column shows "-" or "unknown".

---

### Edge Cases

- What happens with jobs created before this feature? Display "unknown" or "-" for missing provider.
- What happens if provider changes mid-retry? Store the provider used for the successful transcription.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST store the transcription provider name with each job
- **FR-002**: System MUST display the provider in `--status` output
- **FR-003**: System MUST handle legacy jobs without provider data gracefully

### Key Entities

- **Job** (modified): Add `provider` field - the transcription service used ("deepgram" or "assemblyai")

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can identify which provider was used for any job via `--status`
- **SC-002**: Legacy jobs display gracefully without errors
