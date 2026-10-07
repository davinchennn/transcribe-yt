# Video data model

## Storage location

See the [CLI guide](cli.md) for discovering records and retrieving transcripts.

SQLite defaults to `data/transcripts.db`; `STORAGE_PATH` overrides it. Relative
paths use the process working directory. `data/`, `downloads/` and `transcripts/`
may be symlinks. `STORAGE_BACKEND=json` uses `data/state.json`, stores job history,
discovers transcript exports and reports analyses as `not_supported`.

## Identity and units

- `jobs.id`: YouTube video ID or `x-POST_ID[-video-N]`. Match ID and platform;
  titles and speakers do not establish record identity.
- Video platform comes from `jobs.url`. `jobs.provider` means Deepgram/AssemblyAI.
- `duration`: seconds. Word, utterance, node and passage `start/end`: milliseconds.
- Source indices: zero-based, inclusive. Node IDs are scoped to a job and view.
- Database `created_at/updated_at`: UTC ISO strings without an explicit UTC suffix.

## SQLite tables

Child tables join through `job_id = jobs.id`. Transcripts and whole-video
analyses are unique per job; navigation is unique per `(job_id, view)`.

| Table | Columns |
|---|---|
| `jobs` | `id`, `url`, `stage`, `title`, `error`, `provider`, `video_file`, `audio_file`, `transcript_file`, `keep_video`, `keep_audio`, `created_at`, `updated_at` |
| `transcripts` | `id`, `job_id`, `video_url`, `title`, `duration`, `transcript_text`, `words`, `utterances`, `metadata`, `created_at` |
| `analyses` | `id`, `job_id`, `status`, `summary`, `key_points`, `model`, `provider`, `error`, `created_at`, `updated_at` |
| `navigation_analyses` | `id`, `job_id`, `view`, `status`, `summary`, `nodes`, `model`, `provider`, `error`, `created_at`, `updated_at` |

`transcripts_fts(title, transcript_text)` is a derived search index; its `rowid`
matches `transcripts.id`. FTS shadow tables and `sqlite_sequence` are bookkeeping.

## JSON columns and visualization

JSON is stored as TEXT:

```text
transcripts.words[]: {text, start, end, confidence, speaker}
analyses.key_points[]: string
navigation_analyses.nodes[]: {id, title, summary, start, end, children[], occurrences[]}
occurrences[]: {id, start, end, text, utterance_start, utterance_end, word_start?, word_end?}
```

`children` recursively contains nodes. `view` selects `timeline` or `topics`;
each has independent persisted results. For recurring topics, render actual
`occurrences`: a node's bounding `start/end` can include gaps.

`transcripts.metadata` holds flexible download/transcription metadata, including
source, uploader, description, language, model and request ID. Older rows may
lack newer keys. Current writes leave `utterances` NULL; reads derive turns from
words using speaker changes or pauses exceeding one second.

Analysis statuses: `pending`, `processing`, `completed`, `failed`. Inventory
synthesizes `not_created` when no analysis row exists. Search results, playback
position and selections are not persisted. Frontend cache changes do not delete
saved analyses. Replacing transcript text or words invalidates both navigation views.

## Files and access

Media bytes live outside SQLite; `jobs.*_file` stores pointers. Missing exports
do not imply missing database transcripts. Check existence: retention cleanup can
leave stale paths. API `video_available` also requires a completed job, retained
video and a file inside resolved `downloads/videos`.

`GET /api/jobs/JOB_ID` returns completed transcripts, derived utterances, summary
and navigation. `GET /api/jobs/JOB_ID/navigation/VIEW` returns one saved view.
API responses omit stored metadata and filesystem paths; inspect SQLite for those.

[sqlite.py](../packages/core/src/transcripts/storage/sqlite.py) defines schema
bootstrap and conditional alterations; there are no versioned migrations.
Inspect deployed columns with `PRAGMA table_info(TABLE)`. Foreign keys are
declared but connection-level enforcement is not enabled.

Analysis and navigation `provider` identifies the inference service (`kimi` or
`fireworks`); `model` stores the exact model ID used at creation. Existing SQLite
rows migrate to `provider = kimi`; older serialized records also default to Kimi.
This is independent of `jobs.provider`, which identifies the transcription service.
Subtopic summary updates preserve creation metadata and the existing hierarchy.
Each job keeps one summary and one result per navigation view; regeneration replaces
that result rather than storing per-model history.
