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
availability, saved-analysis counts and the newest analysis's status. Use `--query`
to match a title, URL or ID without case sensitivity; combine it with `--source`,
`--id` or `--stage` to select the right video.

`--json` also includes duration in seconds, word count, word-timing availability,
analysis IDs, names, prompts, visualization types, providers and models, update times and errors, node counts and hierarchy
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

## Create and manage saved analyses

Each completed transcript can have several named analyses. Each new analysis
includes a summary, key points and one visualization: `timeline` or `topics`.
Prompts refine the existing output format; Timeline always covers the entire
video chronologically. Creating or regenerating an analysis preserves earlier
versions and does not transcribe or download the video again.

```bash
transcribe analyze --id JOB_ID --view timeline --name "Engineering perspective" --prompt "Emphasize engineering tradeoffs"
transcribe analyze --id JOB_ID --view topics --name "Hiring advice" --prompt-file focus.txt --provider fireworks --model MODEL_ID
transcribe analyses --id JOB_ID --json
transcribe analysis --id JOB_ID --analysis-id ANALYSIS_ID --json
transcribe analyze --id JOB_ID --from-analysis ANALYSIS_ID --prompt "Explain the tradeoffs in greater detail" --json
transcribe analysis --id JOB_ID --analysis-id ANALYSIS_ID --delete
```

`analyze` waits for generation and saves the result with a new analysis ID. With
`--from-analysis`, omitted name, visualization, prompt and inference settings
come from that saved analysis. Any overrides apply only to the new version.
Choosing a different provider without a model uses that provider's configured
default. A migrated summary-only analysis needs an explicit `--view` to generate
a visualization. Empty prompts are allowed; `--prompt ""` clears inherited focus.
Names need not be unique. Use exact analysis IDs to distinguish versions.

`analyses` lists newest first. `analysis` reads one complete result, including its
visualization nodes with `--json`. Both reads use SQLite in read-only mode;
they do not initialize or migrate storage or make model requests. `list --json`
includes an `analyses` collection, `analysis_count` and `analyses_supported` for
each video. Before an old database is first opened by the updated app, read-only
commands describe old results using their eventual imported IDs; they do not
migrate storage. Storage initialization imports and verifies those results, then
removes the old analysis tables.

Generation requires SQLite storage and a configured inference API key. The JSON
backend retains its existing job/transcript support. Failed generated analyses
remain saved with their error; `analyze` exits with status 1 on failure and status
2 for invalid command arguments. `--json` writes the saved result to stdout.
Deleting an analysis leaves the transcript and other analyses intact.
