# Research: File Retention Options

**Feature**: 008-file-retention
**Date**: 2026-02-02

## Research Tasks

### 1. How to modify yt-dlp to always download video first, then extract audio

**Decision**: Modify the download flow to use a two-step process

**Rationale**:
- Current behavior with `extract_audio=True` uses yt-dlp's FFmpegExtractAudio postprocessor which downloads audio-only stream and converts to MP3
- To get both video and audio, we need to:
  1. Download full video (bestvideo+bestaudio merged to mp4)
  2. Extract audio from the downloaded video using FFmpeg separately (or yt-dlp postprocessor)
- yt-dlp supports `--keep-video` flag which keeps the video after audio extraction

**Alternatives considered**:
- Download video and audio separately: Rejected - wastes bandwidth, downloads twice
- Use yt-dlp `--keep-video` option: Viable but less control over file locations

**Implementation approach**:
```python
# Step 1: Download video to videos/ directory
ydl_opts = {
    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "outtmpl": str(self.video_dir / "%(title)s.%(ext)s"),
}

# Step 2: Extract audio from video using FFmpeg postprocessor
# with keepvideo=True to retain the original
ydl_opts = {
    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "outtmpl": str(self.video_dir / "%(title)s.%(ext)s"),
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    }],
    "keepvideo": True,  # Keep original video after extraction
}
```

### 2. Best practice for file cleanup after processing

**Decision**: Clean up files at the end of `process_video()` after successful completion

**Rationale**:
- Cleanup should only happen after `Stage.COMPLETED` is set
- Use try/except around file deletion to handle failures gracefully
- Log cleanup actions for debugging
- Store retention preferences in Job model so cleanup knows what to do

**Implementation approach**:
```python
def _cleanup_files(self, job: Job) -> None:
    """Clean up files based on retention settings."""
    if not job.keep_video and job.video_file:
        try:
            Path(job.video_file).unlink(missing_ok=True)
            logger.info(f"Deleted video file: {job.video_file}")
        except Exception as e:
            logger.warning(f"Failed to delete video file: {e}")

    if not job.keep_audio and job.audio_file:
        try:
            Path(job.audio_file).unlink(missing_ok=True)
            logger.info(f"Deleted audio file: {job.audio_file}")
        except Exception as e:
            logger.warning(f"Failed to delete audio file: {e}")
```

### 3. CLI argument patterns for boolean options

**Decision**: Use `--no-keep-video` and `--no-keep-audio` flags (defaults are True)

**Rationale**:
- argparse convention: `--flag` enables, `--no-flag` disables
- Since defaults are True, users will use `--no-keep-video` to disable retention
- Can also support explicit `--keep-video` / `--no-keep-video` pair using `BooleanOptionalAction`

**Implementation approach**:
```python
parser.add_argument(
    "--keep-video/--no-keep-video",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Keep video file after transcription (default: keep)"
)
parser.add_argument(
    "--keep-audio/--no-keep-audio",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Keep audio file after transcription (default: keep)"
)
```

Note: `BooleanOptionalAction` requires Python 3.9+. For 3.8 compatibility, use:
```python
parser.add_argument("--keep-video", action="store_true", default=True, dest="keep_video")
parser.add_argument("--no-keep-video", action="store_false", dest="keep_video")
```

### 4. SQLite schema migration for new fields

**Decision**: Add columns with defaults, no migration script needed

**Rationale**:
- SQLite supports `ALTER TABLE ADD COLUMN` with default values
- New boolean columns can default to 1 (True) for backwards compatibility
- Existing jobs won't have retention preferences, so defaults apply

**Implementation approach**:
- Check if columns exist in `_init_tables()`
- Add columns if missing: `ALTER TABLE jobs ADD COLUMN keep_video INTEGER DEFAULT 1`
- JSON storage auto-handles new fields via `dict.get()` with defaults

## Summary

All research tasks completed. No blocking unknowns remain. Ready for Phase 1 design.
