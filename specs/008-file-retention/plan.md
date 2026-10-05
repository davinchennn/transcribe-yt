# Implementation Plan: File Retention Options

**Branch**: `008-file-retention` | **Date**: 2026-02-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-file-retention/spec.md`

## Summary

Add configurable file retention options (`keep_video`, `keep_audio`) to control whether video and audio files are retained after transcription. Change default behavior to always download full video first, then extract audio. Both options default to `true`. Files are automatically cleaned up after successful transcription based on user preferences, but retained on failure for debugging/retry.

## Technical Context

**Language/Version**: Python 3.8.1+
**Primary Dependencies**: yt-dlp, FastAPI, Pydantic
**Storage**: SQLite (primary), JSON (fallback) - via storage backends
**Testing**: pytest
**Target Platform**: Linux/macOS (CLI + API server)
**Project Type**: Monorepo with packages (core, api, web)
**Performance Goals**: N/A (file operations are I/O bound)
**Constraints**: Must retain files on failure for retry capability
**Scale/Scope**: Single-user local tool

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution is not configured for this project (template placeholder). No gates to enforce.

## Project Structure

### Documentation (this feature)

```text
specs/008-file-retention/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
packages/
├── core/
│   └── src/transcripts/
│       ├── models.py        # Job model - add keep_video, keep_audio fields
│       ├── downloader.py    # Modify to always download video first
│       ├── processor.py     # Add cleanup logic after transcription
│       ├── cli/main.py      # Add --keep-video, --keep-audio CLI args
│       └── storage/
│           ├── base.py      # Storage interface (no changes)
│           ├── sqlite.py    # May need migration for new fields
│           └── json.py      # Auto-handles new fields
├── api/
│   └── src/api/
│       ├── schemas.py       # Add keep_video, keep_audio to JobCreate
│       └── routes.py        # Pass retention options to processor
└── web/
    └── src/                 # Optional: UI for retention options
```

**Structure Decision**: Existing monorepo structure with core/api/web packages. Changes span core (models, downloader, processor, CLI) and api (schemas, routes). Web UI changes are optional/deferred.

## Complexity Tracking

No violations - feature is straightforward extension of existing functionality.
