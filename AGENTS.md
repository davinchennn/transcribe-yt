# Repository guide

- `packages/core`: models, storage, transcription, analysis and CLI.
- `packages/api`: FastAPI routes and response schemas.
- `packages/web`: React transcript navigation and video playback.

## Find data

Use the [CLI guide](doc/cli.md) to discover saved records and retrieve transcripts.
Run commands from the repository root using the project environment.

Confirm the platform and exact job ID before comparing records or diagnosing a
view. Titles can match across independent uploads. Use the inventory's resolved
storage path; directories may be symlinks and relative paths depend on the
working directory.

Read [doc/data-model.md](doc/data-model.md) for columns, JSON structures and units.
Use inventory or API reads for discovery. Direct SQLite inspection requires
`mode=ro`; constructing `SQLiteStorage` initializes schema.
Update the CLI guide when commands or their output change; update the data guide
when storage contracts change.

## Validate changed code

Run checks for the affected packages:

```bash
.venv/bin/python -m unittest discover -s packages/core/tests
.venv/bin/python -m unittest discover -s packages/api/tests
npm --prefix packages/web run build
npm --prefix packages/web run lint
npm --prefix packages/web test
```
