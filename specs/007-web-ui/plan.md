# Implementation Plan: Web UI

## Phase 1: FastAPI Backend

### 1.1 Create packages/api/ structure
```
packages/api/
├── pyproject.toml
├── src/api/
│   ├── __init__.py
│   ├── main.py          # FastAPI app
│   ├── routes.py         # API endpoints
│   └── schemas.py        # Pydantic models
└── CLAUDE.md
```

### 1.2 API Endpoints
- `GET /api/jobs` - List all jobs
- `POST /api/jobs` - Create job from URL
- `GET /api/jobs/{id}` - Get job with transcript
- `POST /api/jobs/{id}/retry` - Retry failed job
- `DELETE /api/jobs/{id}` - Delete job
- `GET /api/health` - Health check

### 1.3 Add to workspace
- Update root pyproject.toml
- Run uv sync

## Phase 2: React Frontend

### 2.1 Create packages/web/ with Vite
```
packages/web/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/client.ts     # API client
│   ├── components/
│   │   ├── JobList.tsx
│   │   ├── JobRow.tsx
│   │   ├── SubmitForm.tsx
│   │   └── TranscriptView.tsx
│   └── hooks/
│       └── useJobs.ts
└── CLAUDE.md
```

### 2.2 Features
- Job dashboard with status indicators
- URL submission form
- Transcript viewer modal/panel
- Polling for status updates

## Phase 3: Integration

### 3.1 Development setup
- API on :8000, frontend on :5173
- Vite proxy for /api routes

### 3.2 Scripts
- `uv run api` - Start API server
- `npm run dev` - Start frontend dev server

## Files to Create

1. packages/api/pyproject.toml
2. packages/api/src/api/__init__.py
3. packages/api/src/api/main.py
4. packages/api/src/api/routes.py
5. packages/api/src/api/schemas.py
6. packages/api/CLAUDE.md
7. packages/web/* (Vite scaffold + components)
