# transcripts

YouTube video transcription monorepo.

## Structure

```
packages/
├── core/       # Python library + CLI
├── api/        # FastAPI backend
└── web/        # React frontend
specs/          # Feature specifications
```

Runtime data directories (`data/`, `downloads/`, `transcripts/`) are documented in [README.md](README.md#data-directories).

## Quick Start

```bash
# Start API server
uv run api

# Start frontend (in another terminal)
cd packages/web && npm run dev
```

Open http://localhost:5173

## Active Technologies
- Python 3.8.1+ + yt-dlp, FastAPI, Pydantic (008-file-retention)
- SQLite (primary), JSON (fallback) - via storage backends (008-file-retention)
- Moonshot AI (Kimi) for transcript analysis (009-kimi-analysis)

## Environment Variables
- `MOONSHOT_API_KEY` - Required for Kimi transcript analysis

## Recent Changes
- 009-kimi-analysis: Added Kimi transcript analysis (Moonshot AI)
- 008-file-retention: Added Python 3.8.1+ + yt-dlp, FastAPI, Pydantic
