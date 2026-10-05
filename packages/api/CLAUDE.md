# API Package

FastAPI backend for transcripts.

## Commands

```bash
uv run api                    # Start dev server on :8000
uv run uvicorn api.main:app --reload  # Alternative
```

## Endpoints

```
GET  /api/health              # Health check
GET  /api/jobs                # List jobs (?stage=completed)
POST /api/jobs                # Create job {"url": "..."}
GET  /api/jobs/{id}           # Get job + transcript
POST /api/jobs/{id}/retry     # Retry failed job
DELETE /api/jobs/{id}         # Delete job
DELETE /api/jobs              # Clear jobs (?stage=failed)
```

## Code Patterns

- Routes in `api/routes.py`
- Pydantic schemas in `api/schemas.py`
- Uses `transcripts` package for processing
- Background tasks for long-running transcription
