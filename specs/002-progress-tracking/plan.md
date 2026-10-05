# Implementation Plan: Progress Tracking

**Branch**: `002-progress-tracking` | **Date**: 2026-01-25 | **Spec**: [spec.md](./spec.md)

## Summary

Add job state persistence and resume capability to the transcription pipeline. Jobs are tracked through stages (pending → downloading → extracting → transcribing → saving → completed) with state saved to a JSON file after each transition. Failed jobs can be resumed from their last successful stage.

## Technical Context

**Language/Version**: Python 3.8+
**Primary Dependencies**: Existing (yt-dlp, assemblyai, deepgram-sdk, python-dotenv) + filelock for safe concurrent access
**Storage**: JSON file (`.transcripts-state.json` in project root)
**Testing**: pytest
**Target Platform**: macOS, Linux (CLI tool)
**Project Type**: Single project (extends existing structure)
**Performance Goals**: State file operations < 50ms
**Constraints**: State file < 10MB (sufficient for ~10k job records)
**Scale/Scope**: Local single-user usage, hundreds of jobs

## Constitution Check

*No project constitution defined yet. Proceeding with standard Python project practices.*

## Project Structure

### Documentation (this feature)

```text
specs/002-progress-tracking/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
└── checklists/
    └── requirements.md  # Already created
```

### Source Code (repository root)

```text
src/transcripts/
├── __init__.py
├── cli/
│   ├── __init__.py
│   └── main.py          # MODIFY: Add --status, --retry-failed, --clear-* flags
├── config.py
├── converter.py
├── downloader.py
├── models.py            # MODIFY: Add Job, Stage models
├── processor.py         # MODIFY: Integrate state tracking
├── transcriber.py
└── state.py             # NEW: StateManager class

tests/
└── test_state.py        # NEW: State management tests
```

**Structure Decision**: Extends existing single-project structure. New `state.py` module handles all persistence logic. Models extended in existing `models.py`.

## Implementation Approach

### Phase 1: Core State Management
1. Add `Job` and `Stage` models to `models.py`
2. Create `state.py` with `StateManager` class
3. Implement JSON persistence with file locking

### Phase 2: Pipeline Integration
1. Modify `TranscriptProcessor` to create/update jobs
2. Add stage transitions at each pipeline step
3. Implement file existence verification for resume

### Phase 3: CLI Commands
1. Add `--status` flag to show all jobs
2. Add `--retry-failed` flag to retry failed jobs
3. Add `--clear-completed` and `--clear-all` flags
4. Auto-detect and resume when same URL is re-submitted

## Complexity Tracking

No constitution violations - straightforward feature addition following existing patterns.
