# Data Model: Progress Tracking

**Feature**: 002-progress-tracking
**Date**: 2026-01-25

## Entities

### Stage (Enum)

Represents the current step in the transcription pipeline.

| Value | Description |
|-------|-------------|
| `pending` | Job created, not yet started |
| `downloading` | Video download in progress |
| `extracting` | Audio extraction in progress |
| `transcribing` | Transcription API call in progress |
| `saving` | Writing output files |
| `completed` | Successfully finished |
| `failed` | Error occurred |

### Job

Represents a single transcription task.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | YouTube video ID (extracted from URL) |
| `url` | string | Original YouTube URL |
| `title` | string | Video title (populated after download) |
| `stage` | Stage | Current pipeline stage |
| `error` | string? | Error message if failed |
| `video_file` | string? | Path to downloaded video |
| `audio_file` | string? | Path to extracted audio |
| `transcript_file` | string? | Path to output transcript |
| `created_at` | datetime | When job was created |
| `updated_at` | datetime | When job was last modified |

**Validation rules**:
- `id` must be a valid YouTube video ID (11 characters)
- `stage` must be a valid Stage value
- `error` is only set when `stage` is `failed`
- File paths are relative to project root

### State File Structure

```json
{
  "version": 1,
  "jobs": {
    "dQw4w9WgXcQ": {
      "id": "dQw4w9WgXcQ",
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "title": "Video Title",
      "stage": "completed",
      "error": null,
      "video_file": "downloads/video-title.mp4",
      "audio_file": "downloads/video-title.mp3",
      "transcript_file": "transcripts/video-title.json",
      "created_at": "2026-01-25T10:30:00Z",
      "updated_at": "2026-01-25T10:35:00Z"
    }
  }
}
```

## State Transitions

```
                    ┌─────────┐
                    │ pending │
                    └────┬────┘
                         │
                         ▼
                  ┌─────────────┐
                  │ downloading │
                  └──────┬──────┘
                         │
                         ▼
                  ┌─────────────┐
                  │ extracting  │
                  └──────┬──────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ transcribing │
                  └──────┬───────┘
                         │
                         ▼
                    ┌────────┐
                    │ saving │
                    └───┬────┘
                        │
                        ▼
                  ┌───────────┐
                  │ completed │
                  └───────────┘

    Any stage can transition to "failed" on error.
    "failed" can transition back to retry from last checkpoint.
```

## Indexes / Lookups

- **By ID**: Primary lookup for resume/duplicate detection
- **By stage**: Filter for `--status` display and `--retry-failed`
- **By updated_at**: Sort for status display (most recent first)
