# Transcripts

Download YouTube videos and generate transcripts using Deepgram or AssemblyAI.

## Quick Start

```bash
# 1. Setup
python3 -m venv venv
source venv/bin/activate
pip install -e .

# 2. Configure API key
cp .env.example .env
# Edit .env: set DEEPGRAM_API_KEY or ASSEMBLYAI_API_KEY

# 3. Transcribe
transcribe "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Data Directories

Three directories are auto-created in the project root on first run:

| Directory      | Contents                                  |
|----------------|-------------------------------------------|
| `data/`        | SQLite DB (`transcripts.db`) and job state |
| `downloads/`   | Downloaded audio/video files              |
| `transcripts/` | Exported transcripts (JSON/TXT)           |

All three are gitignored. To keep bulky media or the DB outside the repo, replace any of them with a symlink — the app follows symlinks transparently. Override the DB location specifically with `STORAGE_PATH=/custom/path.db`.

## CLI Options

```bash
transcribe URL                          # Single video
transcribe --playlist URL               # Playlist
transcribe --file urls.txt              # Batch (one URL per line)
transcribe --provider assemblyai URL    # Use AssemblyAI instead of Deepgram
transcribe --no-video URL               # Audio only, skip video download
```

## Python API

```python
from transcripts import TranscriptProcessor

processor = TranscriptProcessor()
transcript = processor.process_video("https://youtube.com/watch?v=...")

print(transcript.title)
print(transcript.transcript_text)
```

## Requirements

- Python 3.8+
- FFmpeg
- API key: [Deepgram](https://deepgram.com) or [AssemblyAI](https://assemblyai.com)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `command not found: transcribe` | Run `pip install -e .` with venv activated |
| `No module named ...` | Run `pip install -e .` with venv activated |
| `bad interpreter` | Delete `venv/`, recreate, reinstall |
