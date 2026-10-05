# CLI Contract: File Retention Options

**Feature**: 008-file-retention

## New Arguments

### `--keep-video` / `--no-keep-video`

```
--keep-video          Keep video file after transcription (default)
--no-keep-video       Delete video file after transcription
```

**Type**: Boolean flag pair
**Default**: `True` (keep video)
**Applies to**: `transcribe <url>` command

### `--keep-audio` / `--no-keep-audio`

```
--keep-audio          Keep audio file after transcription (default)
--no-keep-audio       Delete audio file after transcription
```

**Type**: Boolean flag pair
**Default**: `True` (keep audio)
**Applies to**: `transcribe <url>` command

## Usage Examples

### Default behavior (keep both files)
```bash
uv run transcribe https://www.youtube.com/watch?v=VIDEO_ID
# Downloads video, extracts audio, transcribes, keeps both files
```

### Keep audio only
```bash
uv run transcribe https://www.youtube.com/watch?v=VIDEO_ID --no-keep-video
# Downloads video, extracts audio, transcribes, deletes video, keeps audio
```

### Keep transcript only (no media files)
```bash
uv run transcribe https://www.youtube.com/watch?v=VIDEO_ID --no-keep-video --no-keep-audio
# Downloads video, extracts audio, transcribes, deletes both files
```

### Keep video only
```bash
uv run transcribe https://www.youtube.com/watch?v=VIDEO_ID --no-keep-audio
# Downloads video, extracts audio, transcribes, keeps video, deletes audio
```

## Output Changes

### Cleanup logging
When files are deleted, the CLI outputs:
```
Deleted video file: downloads/videos/video-title.mp4
Deleted audio file: downloads/audio/video-title.mp3
```

### Failure handling
When file deletion fails, the CLI outputs a warning but does not fail:
```
Warning: Failed to delete video file: [error message]
```

## Help Text

```
usage: transcribe [-h] [--keep-video | --no-keep-video]
                  [--keep-audio | --no-keep-audio] ...

File Retention:
  --keep-video          Keep video file after transcription (default)
  --no-keep-video       Delete video file after successful transcription
  --keep-audio          Keep audio file after transcription (default)
  --no-keep-audio       Delete audio file after successful transcription
```
