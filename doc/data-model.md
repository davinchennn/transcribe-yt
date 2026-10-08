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
- Source indices: zero-based, inclusive.
- Saved analyses use UUID IDs independent of the job/video ID. Node IDs within
  their visualizations are scoped to the saved analysis.
- Database `created_at/updated_at`: UTC ISO strings without an explicit UTC suffix.

## SQLite tables

Child tables join through `job_id = jobs.id`. Transcripts remain unique per job.
`video_analyses` holds multiple independent saved analyses for each transcript.

| Table | Columns |
|---|---|
| `jobs` | `id`, `url`, `stage`, `title`, `error`, `provider`, `video_file`, `audio_file`, `transcript_file`, `keep_video`, `keep_audio`, `created_at`, `updated_at` |
| `transcripts` | `id`, `job_id`, `video_url`, `title`, `duration`, `transcript_text`, `words`, `metadata`, `created_at` |
| `video_analyses` | `id`, `job_id`, `name`, `view`, `prompt`, `status`, `summary`, `key_points`, `nodes`, `provider`, `model`, `error`, `created_at`, `updated_at`, `source_hash` |
| `schema_migrations` | `name`, `applied_at` |

New saved analyses require `view = timeline` or `topics`. Each includes its own
summary, key points and visualization nodes. `prompt` contains supplemental focus
instructions; an empty string means the standard analysis. Timeline's full-video
chronological coverage remains mandatory. Provider/model and prompt belong to
the saved version. Regeneration creates a new ID and preserves earlier results.
Names need not be unique. Results are ordered by creation time, newest first;
updates to processing status do not reorder them.

The `saved_analysis_versions_v1` migration imports each existing whole-video
summary as a “General summary” analysis with `view = NULL`, and each navigation
view as a separate “Timeline” or “Topics” analysis. It preserves summaries,
points/nodes, provider/model, statuses, errors and timestamps, without inference.
Imported IDs are deterministic UUIDs. The migration marker makes this a one-time
import; deleted results do not reappear when storage is reopened. Summary-only
records remain readable and require a visualization choice to create a new version.
The `saved_analysis_cleanup_v2` upgrade verifies preserved records before dropping
the old `analyses` and `navigation_analyses` tables in the same transaction. If an
old cache changed after its original import, the changed result is preserved as
another version. Intentionally deleted original imports remain deleted.
The unused `transcripts.utterances` column is also removed; any saved turns are
preserved in `metadata._stored_utterances` before removal. Fresh databases create
only the current tables and columns.

`transcripts_fts(title, transcript_text)` is a derived search index; its `rowid`
matches `transcripts.id`. FTS shadow tables and `sqlite_sequence` are bookkeeping.

## JSON columns and visualization

JSON is stored as TEXT:

```text
transcripts.words[]: {text, start, end, confidence, speaker}
video_analyses.key_points[]: string
video_analyses.nodes[]: {id, title, summary, start, end, children[], occurrences[]}
occurrences[]: {id, start, end, text, utterance_start, utterance_end, word_start?, word_end?}
```

`children` recursively contains nodes. `view` selects `timeline` or `topics`;
each has independent persisted results. For recurring topics, render actual
`occurrences`: a node's bounding `start/end` can include gaps.

`transcripts.metadata` holds flexible download/transcription metadata, including
source, uploader, description, language, model and request ID. Older rows may
lack newer keys. Reads derive turns from words using speaker changes or pauses
exceeding one second. Utterance-only transcripts and migrated stored turns use
`metadata._stored_utterances`, an array of `{speaker, text, start, end, confidence}`.
These turns are used when word timings are absent; derivation from words takes
precedence. The API still returns `utterances` as part of each transcript.

Analysis statuses: `pending`, `processing`, `completed`, `failed`. Inventory
synthesizes `not_created` when no analysis row exists. Search results, playback
position and selections are not persisted. Frontend cache changes do not delete
saved analyses. Replacing transcript text, words or effective stored turns
invalidates all saved analyses for that transcript.

`source_hash` fingerprints the transcript text, words and derived utterances used
to reserve a new analysis. Pending work is claimed once. Completion checks both
the original source hash and the still-existing reservation before updating;
deleting an analysis or replacing its transcript prevents a running model request
from restoring stale results. Deleting a job or clearing jobs removes their saved
analyses. Media retention remains attached to the job.

## Files and access

Media bytes live outside SQLite; `jobs.*_file` stores pointers. Missing exports
do not imply missing database transcripts. Check existence: retention cleanup can
leave stale paths. API `video_available` also requires a completed job, retained
video and a file inside resolved `downloads/videos`.

`GET /api/jobs/JOB_ID` returns the completed transcript, its effective utterances,
and the saved `analyses` collection.
API responses omit stored metadata and filesystem paths; inspect SQLite for those.
`GET /api/jobs/JOB_ID/analyses/ANALYSIS_ID` returns one complete saved analysis,
including its prompt, summary/key points and visualization nodes. Analysis IDs
are checked against the requested job; reads never create results.

[sqlite.py](../packages/core/src/transcripts/storage/sqlite.py) defines schema
bootstrap and conditional alterations; `schema_migrations` records applied upgrades.
Inspect deployed columns with `PRAGMA table_info(TABLE)`. Foreign keys are
declared but connection-level enforcement is not enabled.

Analysis `provider` identifies the inference service (`kimi` or
`fireworks`); `model` stores the exact model ID used at creation. Existing SQLite
rows migrate to `provider = kimi`; older serialized records also default to Kimi.
This is independent of `jobs.provider`, which identifies the transcription service.
The saved-analysis endpoints and CLI always create another independent version.
