# CLI guide

Run from the repository root with the project environment activated, or use
`.venv/bin/transcribe` in place of `transcribe`.

## Transcribe videos

```bash
transcribe URL                          # Single video
transcribe --playlist URL               # Playlist
transcribe --file urls.txt              # Batch (one URL per line)
transcribe --provider assemblyai URL    # Use AssemblyAI instead of Deepgram
transcribe --no-video URL               # Audio only, skip video download
```

## List saved records

```bash
transcribe list                         # List saved videos and available data
transcribe list --query Lauren --source x --json
transcribe list --id JOB_ID --json
transcribe list --stage completed
```

`transcribe list` replaces `transcribe --status`. It lists full titles, stable
job IDs, video platforms, processing stages, transcription providers, transcript
availability, and separate summary, Timeline and Topics statuses. Use `--query`
to match a title, URL or ID without case sensitivity; combine it with `--source`,
`--id` or `--stage` to select the right video.

`--json` also includes duration in seconds, word count, word-timing availability,
analysis models, update times and errors, navigation node counts and hierarchy
depth, and saved media paths with file-existence checks. `not_created` means
there is no saved analysis; `failed` means an analysis was attempted and failed.
The JSON storage backend reports analyses as `not_supported` and discovers
transcripts through existing exports rather than a database table.

Listing opens existing SQLite storage in read-only mode and never initializes
schema or creates a missing data directory/database. It reads committed WAL
updates while the app is running. The output reports the resolved storage path,
including symlinks. Run from the repository root, or set `STORAGE_PATH` explicitly:
default paths remain relative to the working directory. Listing makes no model
requests and outputs metadata rather than complete transcripts or topic trees.

## Retrieve a saved transcript

```bash
transcribe show --id JOB_ID --json
transcribe show --id JOB_ID             # Readable title, URL and transcript text
```

Use an exact job ID from `transcribe list`. JSON output contains `storage`
(backend and resolved path) and `job` (the inventory record with an expanded
`transcript`). The transcript includes `transcript_text`, stored metadata, words,
and timestamped utterances derived from words when available. Without words,
existing exported utterances are preserved. Plain-text exports have no word
timings.

Missing jobs or unavailable transcripts exit with status 1 and write an error to
stderr. Invalid arguments exit with status 2. JSON output goes to stdout.

Like `list`, `show` reads existing storage without initializing schema, creating
locks, or making model requests. SQLite reads use read-only mode; JSON storage
reads the job's existing JSON or plain-text export.

See the [data model](data-model.md) for field meanings, timestamp units, storage
layout, and record identity. For complete transcription flags and command help:

```bash
transcribe --help
transcribe list --help
transcribe show --help
```
