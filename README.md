# Transcripts

Download YouTube and X/Twitter videos and generate transcripts using Deepgram or AssemblyAI.

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
transcribe "https://x.com/USERNAME/status/POST_ID"
```

## X/Twitter Videos

Submit an `x.com` or `twitter.com` post URL in the web UI or CLI. A post with
multiple videos uses the first video by default; append `/video/N` to select a
specific media attachment. Posts without a downloadable video fail with a
download error.

Keep **Keep video** enabled for X playback in the web UI. The native player uses
the retained download, and transcript words, navigation passages, and search
results seek it using their source timestamps. The transcript remains available
when the video was not retained or has been removed.

Public posts are the initial supported use case. For posts requiring login, set
`TRANSCRIPTS_COOKIES_FILE` to a local Netscape-format cookies file for yt-dlp.
Cookies are optional and protected content may still fail. The app does not
automatically read browser cookies.

## Transcript Analysis

The web UI can summarize completed transcripts using Kimi Code. Set
`KIMI_CODE_API_KEY` in the root `.env` file. This is a separate key from Deepgram
or AssemblyAI and uses `https://api.kimi.com/coding/v1` with `k3`.
Kimi Code access is subject to your membership's client and usage restrictions.

## Topic Navigation

The web archive is at `/` and each transcript has a shareable `/jobs/{id}` URL.
Topics uses `/jobs/{id}?view=topics`; refreshing or using browser Back/Forward
preserves the transcript and selected view. Vite serves these routes during
development and preview. A production web server must serve `index.html` for
frontend routes such as `/jobs/{id}`.

Open a completed transcript in the web UI and choose **Create Timeline** or
**Create Topics**. Each action runs its own Kimi analysis and waits for the view
to finish. Results are saved independently in SQLite, so switching to an existing
view does not make another model request. Failed analyses can be retried.

Subtopics display summaries of at most 20 words using relevant terms from their transcript
passages. For older saved views, choose **Update summaries** to refresh the
summaries while keeping their existing hierarchy and timestamps. Subtopic tiles
have extra vertical space, and selecting a subtopic reveals its full summary.

- **Timeline** shows chronological chapters and nested subtopics as horizontal
  tiles. Chapters and level 2 subtopics stay visible across the full video.
  Select a level 2 subtopic to highlight it and show its level 3 children.
  Each lower row uses the selected parent's time range. Select deeper subtopics
  to reveal their children while keeping earlier rows visible.
  Topic selection does not move playback; timed passages seek the video.
- **Topics** groups recurring subjects and their subtopics, with tracks showing
  every occurrence across the video. All subjects and their nested levels are
  visible together; select an occurrence to watch that passage.
- The YouTube or retained X video player and selected passage share time navigation.
  Clicking a passage or a timed word seeks the player and preserves whether it
  was playing or paused. Only the selected passage appears in the reading pane.
- **Words** search finds literal words and phrases locally. **Meaning** search
  uses a separate Kimi request to find passages matching a description of an
  idea. Search runs within the open video when submitted.

Navigation needs a transcript with source timestamps. Long transcripts are
analyzed in bounded chunks; model-selected passage references are validated and
mapped back to original word/utterance times rather than generated timestamps.
Videos that cannot be embedded still offer timestamped links to YouTube.

The API exposes `GET` and `POST /api/jobs/{id}/navigation/{timeline|topics}` and
`POST /api/jobs/{id}/search` with `{"query": "…", "mode": "exact"}` or
`"mode": "semantic"`. Creation returns the completed result, or HTTP 202 when
another request is already creating that view. Reading a view never creates it.
`GET /api/jobs/{id}/video` serves retained videos with byte ranges for seeking.

## Data Directories

Three directories are auto-created in the project root on first run:

| Directory      | Contents                                  |
|----------------|-------------------------------------------|
| `data/`        | SQLite DB (`transcripts.db`) and job state |
| `downloads/`   | Downloaded audio/video files              |
| `transcripts/` | Exported transcripts (JSON/TXT)           |

All three are gitignored. To keep bulky media or the DB outside the repo, replace any of them with a symlink — the app follows symlinks transparently. Override the DB location specifically with `STORAGE_PATH=/custom/path.db`.

## CLI

See the [CLI guide](doc/cli.md) for transcription commands, saved-record discovery,
and transcript retrieval.

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
