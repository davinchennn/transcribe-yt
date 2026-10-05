# Data Model: File Retention Options

**Feature**: 008-file-retention
**Date**: 2026-02-02

## Entity Changes

### Job (Extended)

The existing `Job` model is extended with two new fields for retention preferences.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `keep_video` | `bool` | `True` | Whether to retain video file after transcription |
| `keep_audio` | `bool` | `True` | Whether to retain audio file after transcription |

**Validation Rules**:
- Both fields are optional booleans
- Defaults to `True` if not specified
- Stored as INTEGER (0/1) in SQLite
- No inter-field dependencies

**State Transitions**:
- Retention preferences are set at job creation
- Preferences are immutable after creation (no update allowed)
- File cleanup occurs only when job reaches `COMPLETED` stage
- Files are retained regardless of preferences when job reaches `FAILED` stage

### Transcript (No Changes)

The `Transcript` model is unchanged. It continues to store `video_file` and `audio_file` paths, which may be `None` after cleanup if retention is disabled.

## Database Schema Changes

### SQLite

```sql
-- Add columns to existing jobs table (migration)
ALTER TABLE jobs ADD COLUMN keep_video INTEGER DEFAULT 1;
ALTER TABLE jobs ADD COLUMN keep_audio INTEGER DEFAULT 1;
```

### JSON Storage

No schema changes required. New fields are handled via `dict.get()` with defaults:
```python
keep_video=data.get("keep_video", True)
keep_audio=data.get("keep_audio", True)
```

## API Schema Changes

### JobCreate (Request)

```python
class JobCreate(BaseModel):
    url: str
    keep_video: bool = True
    keep_audio: bool = True
```

### JobResponse (Response)

The response schema does not expose retention preferences (internal implementation detail). File paths (`video_file`, `audio_file`) in the job remain but may be `None` after cleanup.

## File Lifecycle

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  DOWNLOAD   │ --> │  TRANSCRIBE │ --> │  COMPLETED  │
│             │     │             │     │             │
│ video_file  │     │ audio_file  │     │  cleanup()  │
│ created     │     │ extracted   │     │  based on   │
│             │     │             │     │  keep_*     │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               v
                                        ┌─────────────┐
                                        │   FAILED    │
                                        │             │
                                        │ files kept  │
                                        │ for retry   │
                                        └─────────────┘
```
