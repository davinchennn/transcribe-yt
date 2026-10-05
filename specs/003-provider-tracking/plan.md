# Implementation Plan: Provider Tracking

**Branch**: `003-provider-tracking` | **Date**: 2026-01-29 | **Spec**: [spec.md](./spec.md)

## Summary

Add a `provider` field to the Job model to track which transcription service (Deepgram or AssemblyAI) was used. Display this in the `--status` output.

## Technical Context

**Language/Version**: Python 3.8+
**Primary Dependencies**: Existing (no new dependencies)
**Storage**: JSON file (`.transcripts-state.json`)
**Project Type**: Single project

## Project Structure

### Source Code Changes

```text
src/transcripts/
├── models.py            # MODIFY: Add provider field to Job
├── processor.py         # MODIFY: Pass provider to job updates
└── cli/main.py          # MODIFY: Display provider in status table
```

## Implementation Approach

1. Add `provider: Optional[str]` field to Job dataclass
2. Update `Job.to_dict()` and `Job.from_dict()` to include provider
3. Update `TranscriptProcessor.process_video()` to set job.provider
4. Update `_show_status()` to display provider column
5. Handle legacy jobs (provider=None → display "-")

## Complexity Tracking

No complexity concerns - simple field addition.
