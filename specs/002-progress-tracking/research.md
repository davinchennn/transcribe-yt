# Research: Progress Tracking

**Feature**: 002-progress-tracking
**Date**: 2026-01-25

## State Persistence Format

**Decision**: JSON file with atomic writes

**Rationale**:
- Human-readable for debugging
- No external dependencies
- Matches existing transcript output format
- Atomic write via temp file + rename prevents corruption

**Alternatives considered**:
- SQLite: Overkill for single-user local state
- Pickle: Not human-readable, security concerns
- YAML: Extra dependency, no significant benefit over JSON

## File Locking

**Decision**: Use `filelock` library

**Rationale**:
- Cross-platform (Windows, macOS, Linux)
- Simple API
- Handles edge cases (stale locks, crashes)
- Already a common Python pattern

**Alternatives considered**:
- `fcntl`: Unix-only, not cross-platform
- No locking: Risk of corruption with concurrent access
- Custom lock file: Reinventing the wheel

## Job Identification

**Decision**: Use normalized YouTube video ID as job key

**Rationale**:
- Unique per video
- Allows detecting duplicate submissions
- Can be extracted from various YouTube URL formats
- Stable across retries

**Alternatives considered**:
- UUID: Doesn't prevent duplicate processing
- Full URL: Multiple URL formats for same video would create duplicates

## Stage Transitions

**Decision**: Linear stage progression with validation

**Rationale**:
- Simple state machine: pending → downloading → extracting → transcribing → saving → completed
- Failed state can occur from any stage
- Resume starts from last completed stage

**Stage definitions**:
| Stage | Entry condition | Exit condition |
|-------|-----------------|----------------|
| pending | Job created | Download starts |
| downloading | Download starts | Video file exists |
| extracting | Video exists | Audio file exists |
| transcribing | Audio exists | Transcript received |
| saving | Transcript received | Files written |
| completed | Files written | Terminal state |
| failed | Any error | Can retry |

## Resume Logic

**Decision**: Verify file existence before skipping stages

**Rationale**:
- State file might say "downloaded" but file could be deleted
- Cheap check (file existence) prevents confusing errors later
- Graceful degradation: missing file → restart from that stage

**Implementation**:
```
if job.stage >= "downloading" and not video_file.exists():
    job.stage = "pending"  # Restart download
if job.stage >= "extracting" and not audio_file.exists():
    job.stage = "downloading"  # Re-extract
```
