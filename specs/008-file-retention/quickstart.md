# Quickstart: File Retention Options

**Feature**: 008-file-retention

## Overview

This feature adds configurable file retention options for video and audio files during transcription. By default, both files are kept after transcription completes.

## CLI Usage

### Basic transcription (keeps all files)
```bash
uv run transcribe https://www.youtube.com/watch?v=VIDEO_ID
```

### Transcript only (delete media files)
```bash
uv run transcribe https://www.youtube.com/watch?v=VIDEO_ID --no-keep-video --no-keep-audio
```

### Audio only (delete video)
```bash
uv run transcribe https://www.youtube.com/watch?v=VIDEO_ID --no-keep-video
```

## API Usage

### Create job with default retention (keep both)
```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID"}'
```

### Create job keeping audio only
```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID", "keep_video": false}'
```

### Create job keeping transcript only
```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID", "keep_video": false, "keep_audio": false}'
```

## File Locations

| File Type | Location | Retention Default |
|-----------|----------|-------------------|
| Video | `downloads/videos/` | Kept |
| Audio | `downloads/audio/` | Kept |
| Transcript | Database + `transcripts/` | Always kept |

## Behavior Notes

1. **Default behavior changed**: System now downloads full video first, then extracts audio (previously downloaded audio-only stream)

2. **Failure handling**: If transcription fails, all files are retained regardless of retention settings to allow debugging and retry

3. **Deletion failures**: If file deletion fails (permissions, file locked), a warning is logged but the job still completes successfully

4. **Existing jobs**: Retention settings only apply to new jobs. Existing jobs are unaffected.
