# Core Package

Python library for YouTube transcription with CLI.

## Commands

```bash
# Transcribe a video
uv run transcribe <url>
uv run transcribe <url> --output-format none  # Database only, no files

# Search transcripts
uv run transcribe --search "keyword"

# Export transcript
uv run transcribe --export <job_id> --format json
uv run transcribe --export <job_id> --format txt

# Job management
uv run transcribe list
uv run transcribe list --query Lauren --source x --json
uv run transcribe list --id <job_id> --json
uv run transcribe --retry-failed
uv run transcribe --clear-completed
uv run transcribe --migrate  # JSON to SQLite migration

# Tests
uv run python -m pytest
```

## Environment

```bash
DEEPGRAM_API_KEY=               # Required for Deepgram
ASSEMBLYAI_API_KEY=             # Required for AssemblyAI
TRANSCRIPTION_PROVIDER=deepgram # "deepgram" or "assemblyai"
```

## Storage

Transcripts stored in SQLite with FTS5 full-text search. Utterances are derived from words on-the-fly (not stored).

```bash
STORAGE_BACKEND=sqlite    # "sqlite" (default) or "json"
STORAGE_PATH=             # Optional custom path
```

Default paths and directory layout: see [root README](../../README.md#data-directories).

`transcribe list` opens existing storage read-only and reports the resolved path.
It exposes source identity, transcript/timing availability, existing media, and
independent summary/Timeline/Topics states. It does not initialize schema or
create a missing database. Use an exact job ID or source filter when titles match.

## Code Patterns

- Models in `transcripts/models.py` (Word, Utterance, Transcript, Job)
- Storage backends in `transcripts/storage/` (base.py, sqlite.py, json_storage.py)
- CLI entry point: `transcripts/cli/main.py`

## Recent Changes

- 006-drop-utterances: Derive utterances from words on-the-fly
- 005-transcript-storage: SQLite storage with FTS5 search
- 004-storage-abstraction: Pluggable storage backends
