# Web Package

React frontend for transcripts.

## Commands

```bash
cd packages/web
npm run dev      # Start dev server on :5173
npm run build    # Production build
npm run preview  # Preview production build
```

## Stack

- React 18 + TypeScript
- Vite
- Tailwind CSS
- TanStack Query (server state)

## Structure

```
src/
├── api/client.ts       # API client functions
├── hooks/useJobs.ts    # React Query hooks
├── components/
│   ├── SubmitForm.tsx  # URL input form
│   ├── JobList.tsx     # Job dashboard table
│   ├── JobRow.tsx      # Single job row
│   └── TranscriptView.tsx  # Modal for viewing transcripts
├── App.tsx             # Main app component
└── main.tsx            # Entry point with providers
```

## Development

Frontend proxies `/api` to `localhost:8000` (API server).
Start both servers for development:

```bash
# Terminal 1
uv run api

# Terminal 2
cd packages/web && npm run dev
```
