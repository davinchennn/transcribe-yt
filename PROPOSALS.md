# Feature Proposals

Ideas for future development. Use spec-kit (`/speckit.specify`) to develop any of these.

## Testing & Quality

- [ ] Unit tests for `StateManager`, `Job` model
- [ ] Integration tests for CLI commands
- [ ] Test coverage reporting

## CLI Enhancements

- [ ] `--version` flag
- [ ] Progress bar during download/transcription
- [x] `transcribe list --json` inventory output for scripting
- [ ] `--quiet` / `--verbose` flags

## New Features

- [ ] **Transcript search** - `transcribe --search "keyword"` across all transcripts
- [ ] **Export formats** - SRT/VTT subtitles, Word doc, PDF
- [ ] **LLM summarization** - Generate summary using Kimi K2.5, Claude, OpenAI, etc.
- [ ] **Cost tracking** - Estimate/track API costs per job
- [ ] **Parallel processing** - Process multiple videos concurrently

## Data & Storage

- [ ] SQLite backend (alternative to JSON for larger scale)
- [ ] Transcript tagging/categorization
- [ ] Archive old jobs

## Documentation

- [ ] Update README with CLI commands/options (`transcribe list`, `--retry-failed`, etc.)
- [ ] Add usage examples
- [ ] API documentation for Python library

## Integrations

- [ ] Webhook notifications on completion
- [ ] Slack/Discord alerts
- [ ] S3/cloud storage for outputs
