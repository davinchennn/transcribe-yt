# Transcript JSON data structure (agent reference)

YouTube video transcript export format. Use this when reading or writing transcript JSON files from this project or compatible exporters.

---

## Root object

| Field | Type | Description |
|-------|------|-------------|
| `video_url` | string | Canonical YouTube watch URL (e.g. `https://www.youtube.com/watch?v=...`). |
| `title` | string | Video title as shown on YouTube. |
| `duration` | number | Total video length in **seconds**. |
| `transcript_text` | string | Full transcript as a single blob; punctuation and capitalization as from the source. Use for search/summary; use `words` or `utterances` for timing. |
| `words` | array | Word-level timing and confidence; one entry per token. Order is chronological. |
| `utterances` | array | Speaker-turn level; each entry is one continuous segment from one speaker. Best for “who said what when” and dialogue UI. |

---

## `words[]` — word object

Each element is one spoken word/token with timing and optional confidence.

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | The word as recognized (lowercase in examples). |
| `start` | number | Start time in **milliseconds** from video start. |
| `end` | number | End time in **milliseconds** from video start. |
| `confidence` | number | Recognition confidence in [0, 1]. Optional depending on exporter. |
| `speaker` | string | Speaker id for diarization (e.g. `"0"`, `"1"`). Same id can recur across turns. |

- **Time base:** `start`/`end` are in **ms**. Convert to seconds with `start/1000`.  
- **Order:** Strictly by `start` (and then `end`) so concatenating `text` in order reconstructs the transcript (modulo spacing).  
- **Use for:** Precise highlights, word-level search, confidence filtering, karaoke-style playback.

---

## `utterances[]` — utterance object

Each element is one contiguous segment from a single speaker (one “turn” or part of a turn).

| Field | Type | Description |
|-------|------|-------------|
| `speaker` | string | Speaker id (e.g. `"0"` = guest, `"1"` = host). Map to labels elsewhere if needed. |
| `text` | string | Full text of that segment; usually lowercase, punctuation may vary. |
| `start` | number | Segment start in **milliseconds** from video start. |
| `end` | number | Segment end in **milliseconds** from video start. |

- **Time base:** Same as `words`: **milliseconds**.  
- **Coverage:** Utterances are contiguous in time; concatenating in order (with optional spacing) approximates `transcript_text`.  
- **Use for:** Speaker-attributed quotes, dialogue views, “jump to speaker/turn” UX, and any agent logic that reasons over turns rather than single words.

---

## Relationships

- **Duration:** `duration` (seconds) × 1000 ≈ last `end` in `words` or `utterances` (ms).  
- **Text consistency:** `transcript_text` ≈ concatenation of `utterances[].text` (or `words[].text`) up to normalization (case, spacing, punctuation).  
- **Speaker ids:** Same `speaker` value in `words` and `utterances` refers to the same speaker; ids are ordinal (0, 1, …), not necessarily stable across files.

---

## Example (minimal)

```json
{
  "video_url": "https://www.youtube.com/watch?v=uF2m3OQ7AzE",
  "title": "Warren Pies: The Market Just Did Something...",
  "duration": 3315,
  "transcript_text": "Earnings inflecting higher...",
  "words": [
    { "text": "earnings", "start": 240, "end": 719, "confidence": 0.993, "speaker": "0" },
    { "text": "inflecting", "start": 719, "end": 1220, "confidence": 0.91, "speaker": "0" }
  ],
  "utterances": [
    { "speaker": "0", "text": "earnings inflecting higher...", "start": 240, "end": 34070 },
    { "speaker": "1", "text": "warren pies founder of three fourteen research...", "start": 35090, "end": 44164 }
  ]
}
```

---

## File reference

- **Example file:** `Warren Pies_ The Market Just Did Something That's Never Happened Before — And It's Bullish.json`  
- **Typical size:** Large (e.g. 1.4M+ characters) for long videos due to `words` array (one object per word). Prefer streaming or field-specific parsing when only `title`, `transcript_text`, or `utterances` are needed.
