# Transcript Visualization V1: Design Specification

## Overview

A visualization tool for dissecting long-form video transcripts (60+ minutes) using an icicle diagram with minimap. Users can zoom out to see major themes, zoom in to see granular details down to individual words, and click any element to seek to that moment in a locally-played video.

**Inputs:** Local video file + transcript JSON (pre-generated)
**Core visualization:** Icicle diagram (horizontal timeline, vertical hierarchy)
**Navigation:** Minimap (global) + Detail View (local) + Adaptive Cell Sizing

---

## 1. Interaction Model: Candidates Explored

We evaluated 11 interaction models before converging on the icicle + minimap approach. Below is a summary of each candidate and the rationale for selection or rejection.

### 1.1 Outliner Style
Traditional collapsible tree (Workflowy/Notion pattern). Click arrows to expand/collapse nodes.

**Strengths:** Familiar pattern, handles arbitrary depth, straightforward to implement.
**Weaknesses:** Loses timeline proportionality entirely — a 20-minute topic looks the same as a 2-minute topic. Very linear, no at-a-glance overview. Users must expand each node manually to build a mental map.
**Verdict:** Rejected. Timeline proportionality is a core requirement for video transcript navigation.

### 1.2 Map Zoom (Google Maps Metaphor)
Literal zoom in/out. At high altitude, see topic clusters; zoom in and text appears progressively across discrete zoom levels (Level 0: thesis → Level 4: words).

**Strengths:** Intuitive metaphor that most users already understand. Smooth transitions. Works well on touch devices.
**Weaknesses:** Spatial layout is unclear — where do topics go in 2D space? Hard to maintain timeline alignment when topics are placed spatially. Requires a layout algorithm that doesn't have a natural solution for sequential transcript data.
**Verdict:** Rejected. The spatial layout problem is unsolved for sequential content. The metaphor works for geographic data, not timelines.

### 1.3 Fisheye / Focus+Context
Everything is visible simultaneously. The focused area expands while the periphery compresses proportionally. Click any row to shift focus.

**Strengths:** Never lose global context. Smooth focus transitions. Efficient use of screen space.
**Weaknesses:** Spatial distortion is disorienting — items change position and size as focus shifts. Doesn't naturally encode timeline. Works better for data tables than hierarchical content.
**Verdict:** Rejected. Distortion conflicts with the need for stable spatial mapping to timeline.

### 1.4 Stacked Cards
Topics as expandable cards with nested sub-cards. Standard accordion pattern.

**Strengths:** Clean mobile UX. Infinite nesting. Familiar accordion interaction.
**Weaknesses:** Same problem as outliner — loses timeline proportionality. Hard to compare across topics when cards are expanded at different levels. Vertical scrolling dominates.
**Verdict:** Rejected. Same core limitation as outliner. No timeline encoding.

### 1.5 Concentric Rings (Sunburst)
Radial layout with center as summary, outer rings as deeper hierarchy levels. Angular span encodes duration.

**Strengths:** Compact. Shows proportions clearly. Visually striking and distinctive.
**Weaknesses:** Radial layout breaks timeline — reading direction is angular, not left-to-right. Hard to label segments in a radial layout. Unfamiliar to most users.
**Verdict:** Rejected. Radial encoding conflicts with chronological left-to-right expectation.

### 1.6 Miller Columns (Finder-style)
Three-column drill-down. Select a theme in column 1, see its points in column 2, see detail in column 3.

**Strengths:** Clear drill-down path. No disorientation — each column is a stable list. Scales well to deep hierarchies.
**Weaknesses:** Loses timeline proportionality. Only one drill-down path visible at a time — can't see the structure of Theme 2 while looking at Theme 5's details.
**Verdict:** Rejected. Single-path visibility is too limiting for understanding full transcript structure.

### 1.7 Arc Diagram
Sequential text along a horizontal axis with arcs connecting related segments above.

**Strengths:** Preserves reading order and timeline. Good at showing cross-references and callbacks. Clean visual language.
**Weaknesses:** Not hierarchical — arcs show relationships, not containment. Arcs get cluttered with many connections. Better as a supplementary view than a primary navigation tool.
**Verdict:** Rejected for V1. Potentially valuable as a future layer for cross-theme references.

### 1.8 Hyperbolic Tree
Focus+context tree where the focused node is magnified and distortion falls off radially. Click any node to refocus the view.

**Strengths:** Handles very large trees (100+ nodes) while maintaining global context. Smooth refocusing animation.
**Weaknesses:** Disorienting — the entire tree reshuffles on each click. Loses timeline completely. Better suited for exploration of non-sequential data.
**Verdict:** Rejected. Disorientation and loss of timeline are both disqualifying.

### 1.9 Sentence Centrality Graph (TextRank/LexRank)
Sentences as nodes in a graph, similarity as edges. Node size indicates importance (centrality score).

**Strengths:** Automatically surfaces the most important sentences. Shows relationships between similar content. Computationally well-understood.
**Weaknesses:** No hierarchy. No timeline. Requires precomputed similarity scores. Better for summarization than navigation.
**Verdict:** Rejected. This is a summarization technique, not a navigation interface.

### 1.10 Sankey Diagram
Flow from speakers to topics (or topics to subtopics). Width of flow encodes quantity of contribution.

**Strengths:** Excellent for showing speaker contribution to each topic. Reveals flow patterns. Visually appealing.
**Weaknesses:** Not suitable for drill-down. Loses temporal sequence — shows aggregate flows, not moment-by-moment progression.
**Verdict:** Rejected for V1. Potentially useful as an analytics overlay showing speaker distribution.

### 1.11 RST Tree (Rhetorical Structure Theory)
Discourse structure tree with labeled relations (elaboration, contrast, evidence, cause) connecting segments.

**Strengths:** Linguistically grounded. Shows why segments relate, not just that they do. Rich semantic information.
**Weaknesses:** Complex and unfamiliar to non-linguists. Doesn't scale to long content — trees become unwieldy. Loses timeline.
**Verdict:** Rejected. Relation types are captured in the data model (L2 `relation` field) but not surfaced as the primary visualization.

### 1.12 Icicle Diagram + Minimap — Selected
Horizontal icicle diagram where the x-axis is time and the y-axis is hierarchy depth. Width of each cell encodes duration. A minimap provides global navigation while a detail view shows the current time window at full granularity.

**Strengths:** Preserves horizontal timeline (aligns with video playback). Shows hierarchy top-down (themes → points → evidence → words). Width encodes duration proportionally. Familiar reading direction (left-to-right = chronological). Works naturally with a video playhead.
**Weaknesses:** Cells become unreadable slivers at full zoom-out for long content. Addressed by minimap + detail view + adaptive sizing.
**Verdict:** Selected. Best combination of timeline preservation, hierarchy visualization, and navigability.

---

## 2. Long-Form Content: Strategies Explored

At scale (60+ minutes, 9,000+ words), the raw icicle approach breaks down. We evaluated five strategies for handling this.

### 2.1 Strategy A: Viewport + Minimap — Selected
Modeled after code editors and DAWs. A compressed minimap shows the full video duration (L0/L1 only). A detail view shows a 5–15 minute window at full granularity across all hierarchy levels.

**Strengths:** Proven pattern. Global context always visible. Smooth panning and zooming.
**Selected for V1.**

### 2.2 Strategy B: Semantic Zoom (Non-Time-Linear)
Cells expand/collapse based on focus rather than strict duration. The selected theme takes 60–70% of the width; siblings compress.

**Strengths:** Keeps everything navigable in a single view.
**Weaknesses:** Breaks proportionality — a 5-minute topic could appear wider than a 20-minute topic if focused.
**Rejected.** Proportionality is a core design principle.

### 2.3 Strategy C: Vertical Stack + Horizontal Time
Themes stack vertically (one row per theme), time runs horizontally within each row. Shows when themes recur.

**Strengths:** Reveals recurring topics and temporal patterns across themes.
**Weaknesses:** Wastes vertical space — most rows are mostly empty. Doesn't handle hierarchy below L1 without nesting further.
**Deferred.** Interesting for analytics but not primary navigation.

### 2.4 Strategy D: Two-Stage Navigation
For very long content, force a two-step flow: first pick a theme (card or list), then see the icicle for just that theme's time range.

**Strengths:** Keeps each view manageable regardless of total duration.
**Weaknesses:** Loses global context during the second stage. Users can't see how their selected theme relates to the full timeline.
**Rejected.** Global context loss is disqualifying.

### 2.5 Strategy E: Adaptive Cell Sizing — Selected (Combined with A)
Dynamic rules for collapsing cells that are too small to read. Decisions are made per-level, not per-cell.

**Rule:** If >50% of cells at a given level would be <40px in the current viewport, the entire level collapses. Zoom in to reveal collapsed levels.

**Selected for V1, combined with Strategy A.**

---

## 3. Hierarchy Depth: Options Explored

### 3.1 Option A: 3 LLM levels + word row (L0–L4)
Original design with Themes → Points → Evidence → Words. Four visible icicle rows plus a virtualized word row.

**Rejected.** Too many LLM-generated levels. Evidence vs. Points distinction is content-dependent and unreliable. Virtualized word row adds complexity for little user value.

### 3.2 Option B: 2 LLM levels + word panel (L0–L2 + panel) — Selected
Icicle shows only Topics and Segments. Clicking any L2 cell opens a word panel with flowing text. Simpler LLM task, cleaner visualization, more reliable output.

**Strengths:** Fewer LLM-generated levels = more reliable segmentation. Icicle stays readable. Word panel provides full text access without rendering thousands of cells. Works across content types — topics/segments is generic enough for earnings calls, podcasts, lectures, interviews.
**Weaknesses:** Less hierarchy depth in the icicle. Users can't see evidence-level structure at a glance.

**Selected for V1.** Simplicity, reliability, and content-type flexibility outweigh deeper hierarchy.

---

## 4. V1 Specification

### 4.1 Granularity Levels

| Level | Name | Description | Source |
|-------|------|-------------|--------|
| L0 | Thesis | One sentence: what is this entire transcript about? | LLM-generated |
| L1 | Topics | 3–7 major subjects covered (non-overlapping, exhaustive) | LLM-generated |
| L2 | Segments | How each topic unfolds — subdivisions within each topic | LLM-generated (aligned to utterance boundaries) |
| Panel | Words | Flowing text shown on L2 click, each word clickable to seek | Direct from `words[]` array |

### 4.2 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        VIDEO PLAYER                             │
│                   (HTML5 <video> element)                        │
│                     Local file playback                          │
└─────────────────────────────────────────────────────────────────┘

┌─ Minimap (always visible, full duration) ───────────────────────┐
│ ▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│     └──────┘ ← viewport indicator                               │
│ Shows L0/L1 only. Color-coded by theme. Click to jump.          │
└─────────────────────────────────────────────────────────────────┘

┌─ Detail View (5–15 min window, all visible levels) ─────────────┐
│ ┌─────────────────────────────────────────────────────────────┐  │
│ │ L0: Thesis                                                  │  │
│ ├─────────────┬─────────────────┬─────────────────────────────┤  │
│ │ L1: Topic A │   L1: Topic B   │       L1: Topic C           │  │
│ ├──────┬──────┼────────┬────────┼──────────┬──────────────────┤  │
│ │ L2   │ L2   │  L2    │  L2    │   L2     │      L2          │  │
│ └──────┴──────┴────────┴────────┴──────────┴──────────────────┘  │
│ ◄═══════════════════ horizontal scroll ═══════════════════════►  │
└─────────────────────────────────────────────────────────────────┘

┌─ Word Panel (opens on L2 click) ──────────────────────────────┐
│ Segment: "Revenue growth and margin improvement"               │
│                                                                 │
│  [earnings] [inflecting] [higher] [this] [quarter] [with]      │
│  [revenue] [up] [twenty] [percent] [year] [over] [year]        │
│                                                                 │
│  Click any word to seek. Low-confidence words dimmed.           │
│  Speaker: Speaker 0  │  Duration: 0:12–0:34  │  ✕ Close        │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Input Data

The application accepts two files from the user:

**Video file:** Any format supported by HTML5 `<video>` (mp4, webm). Loaded via file picker or drag-and-drop. Played locally — never uploaded.

**Transcript JSON:** Pre-generated transcript matching this schema:

```json
{
  "title": "Video Title",
  "duration": 3315,
  "transcript_text": "Full transcript as a single string...",
  "words": [
    {
      "text": "earnings",
      "start": 240,
      "end": 719,
      "confidence": 0.99,
      "speaker": "0"
    }
  ],
  "utterances": [
    {
      "speaker": "0",
      "text": "earnings inflecting higher...",
      "start": 240,
      "end": 34070
    }
  ]
}
```

- `start`/`end` are in **milliseconds**
- `utterances[]` = speaker turns, used as the unit for LLM analysis and L2 boundary alignment
- `words[]` = word-level timing for word panel and precise seeking
- Transcript assumed to be pre-generated (Whisper, AssemblyAI, Deepgram, etc.)

### 4.4 LLM Analysis Output Schema

The LLM produces a hierarchy using **verbatim text anchors** instead of timestamps. Timestamps are resolved deterministically in post-processing.

```json
{
  "l0_thesis": "string",
  "l1_topics": [
    {
      "id": "topic-1",
      "title": "string (2–5 words, noun phrase)",
      "summary": "string (1–2 sentences)",
      "starts_with": "first three to five words verbatim",
      "ends_with": "last three to five words verbatim",
      "l2_segments": [
        {
          "id": "seg-1-1",
          "title": "string (short descriptive phrase)",
          "starts_with": "verbatim anchor phrase",
          "ends_with": "verbatim anchor phrase"
        }
      ]
    }
  ]
}
```

**LLM output constraints:**
- `starts_with`/`ends_with`: minimum 3 words, verbatim from transcript
- LLM never produces timestamps directly
- Topic titles: noun phrases, not sentences
- Segment titles: short descriptive phrases
- Topics must be non-overlapping and exhaustive

**L2 boundary constraint:** Each L2 segment must start at the beginning of an utterance and end at the end of an utterance. L2 segments never split mid-utterance. This ensures clean speaker attribution — each L2 segment maps to one or more complete consecutive utterances.

**Speaker attribution for L2:** Derived from constituent utterances. If all utterances share a speaker, single speaker value. If a segment spans a multi-speaker exchange, primary speaker is the one with the most speaking time within that segment.

### 4.5 Timestamp Resolution Pipeline

LLM output uses verbatim text anchors. Timestamps are resolved via deterministic post-processing against the `words[]` array.

**Step 1: Build lookup**
Construct a character-offset-to-word-index map from `transcript_text` and `words[]`. Each character position in the transcript text maps to the word that contains it.

**Step 2: Exact match**
Find `starts_with` and `ends_with` as exact substrings in `transcript_text`. Map the matched character offsets to `words[]` indices. Derive `start_ms` from the matched start word's `start` value and `end_ms` from the matched end word's `end` value.

**Step 3: Fuzzy fallback**
If exact match fails (minor LLM misquote), use sliding-window n-gram matching (3–4 words) against the `words[]` array to find the best match.

**Step 4: Hierarchical scoping**
Resolution cascades top-down. L1 boundaries are resolved first, constraining the search range for L2 matches within each L1. This prevents ambiguity when the same phrase appears multiple times in the transcript.

**Step 5: Validation**
Verify no gaps or overlaps between adjacent segments at each level. If a gap is found, extend the earlier segment's `end_ms` to meet the next segment's `start_ms`. If an overlap is found, adjust the later segment's `start_ms` to the earlier segment's `end_ms`.

### 4.6 LLM Prompt Template

```
You are analyzing a transcript to extract its hierarchical topic structure.

## Granularity Levels

L0 - THESIS: One sentence. What is this entire transcript about?
L1 - TOPICS: 3–7 major subjects covered. Each should be coherent and non-overlapping.
L2 - SEGMENTS: How each topic unfolds — subdivisions within each topic. Must align to utterance boundaries.

## Instructions

1. Read the full transcript
2. Identify L0 thesis
3. Segment into L1 topics — use starts_with/ends_with (minimum 3 words, verbatim)
4. For each topic, identify L2 segments with starts_with/ends_with (must start at the
   beginning of an utterance and end at the end of an utterance)

## Boundary Rules

- starts_with/ends_with must be VERBATIM text from the transcript (minimum 3 words)
- Topics must be NON-OVERLAPPING and EXHAUSTIVE — every word belongs to exactly one topic
- L2 segment boundaries must align to utterance starts/ends — never split mid-utterance

## Output Schema

{
  "l0_thesis": "...",
  "l1_topics": [
    {
      "id": "topic-1",
      "title": "noun phrase (2–5 words)",
      "summary": "1–2 sentences",
      "starts_with": "verbatim 3–5 words",
      "ends_with": "verbatim 3–5 words",
      "l2_segments": [
        {
          "id": "seg-1-1",
          "title": "short descriptive phrase",
          "starts_with": "verbatim 3–5 words",
          "ends_with": "verbatim 3–5 words"
        }
      ]
    }
  ]
}

<transcript>
{{UTTERANCES_WITH_SPEAKER_LABELS}}
</transcript>
```

**For transcripts over 60 minutes, use two-pass analysis:**

Pass 1: Extract L0 and L1 only (thesis + topic boundaries with text anchors). Input: full `utterances[]`.
Pass 2: For each L1 topic, extract L2 segments. Input: utterances within that topic's resolved boundaries. Can be parallelized.

**Cross-topic references:** Not captured in V1. Each topic's analysis is self-contained. Deferred to a future version.

### 4.7 Minimap

- Always visible above the detail view
- Shows full video duration compressed to viewport width
- Renders L0 and L1 only (topics as colored bands)
- Viewport indicator shows which portion of the timeline the detail view currently displays
- Click anywhere on the minimap to jump the detail view to that region
- Drag the viewport indicator to scrub through the video
- Playhead position shown as a thin vertical line

### 4.8 Detail View

- Shows a 5–15 minute window of the timeline at full granularity
- Horizontal scroll pans through the timeline
- Zoom in/out (scroll wheel or pinch) adjusts the time window size
- All visible hierarchy levels rendered as icicle rows
- Vertical playhead line sweeps across during video playback, highlighting active cells

### 4.9 Adaptive Cell Sizing

- Collapse decisions are **per-level**, not per-cell
- If >50% of cells at a given level would be <40px wide in the current viewport, the **entire level** collapses
- Collapsed levels are hidden from the detail view
- Zoom in → time window narrows → cells grow → levels reappear as cells cross the 40px threshold
- The minimap always shows L0/L1 regardless of zoom level

### 4.10 Word Panel (Click-to-Reveal)

- Clicking any L2 segment cell opens a word panel below the icicle diagram
- Panel displays the words within that L2 segment as flowing text
- Words are rendered from the `words[]` array within the L2 cell's resolved time range
- Each word is a clickable element → `video.currentTime = word.start / 1000`
- Low confidence words (`confidence < 0.8`): dimmed text or underline indicator
- Panel header shows: segment title, speaker, time range, close button
- Only one panel open at a time — clicking a different L2 cell replaces the panel content
- During video playback, the current word in the panel is highlighted (scrolled into view if needed)
- Panel inherits the parent topic's color as an accent (border or header background)

### 4.11 Video Player Integration

HTML5 `<video>` element playing local files. No external embeds, no iframe communication, no API keys.

**Seek (icicle → video):**
Click any cell at any level → `video.currentTime = resolved_start_ms / 1000`

**Playhead sync (video → icicle):**
Listen to `timeupdate` event on the video element → update playhead position across all icicle levels and the minimap → highlight active cells at each level

**Playback state:**
`play()`, `pause()`, `playbackRate` available for custom controls if needed. Native browser controls used as default.

### 4.12 Interactions

| Action | Result |
|--------|--------|
| Hover icicle cell | Highlight corresponding region in minimap. Show tooltip (L1: topic title + summary, L2: segment title). |
| Click L1 cell | Seek video to that topic's `start_ms`. |
| Click L2 cell | Open word panel showing that segment's words as flowing text. Seek video to segment start. |
| Click word in panel | Seek video to `word.start`. |
| Scroll horizontally in detail view | Pan through timeline. Minimap viewport indicator moves accordingly. |
| Zoom in/out (scroll wheel or pinch) | Adjust detail view time window. L2 appears/disappears based on per-level collapse rules. |
| Video plays | Playhead moves across icicle. Current cells at each level are highlighted. Current word in panel highlighted. |
| Click minimap | Jump detail view to that region. |
| Drag minimap viewport | Scrub through video timeline. |

### 4.13 Visual Design

- **Color-coding:** Each L1 topic has a distinct color. L2 cells within a topic inherit the topic's color at lighter saturation. Word panel uses the parent topic's color as an accent.
- **Speaker indication:** Subtle left border color or small icon in L2 cells to indicate speaker. Word panel header shows speaker label.
- **Playhead:** Vertical line across all icicle levels (L0–L2) in the detail view and the minimap. Distinct color (e.g., red or white).
- **Confidence:** Low-confidence words (`< 0.8`) shown as dimmed text in the word panel.
- **Active cells:** During playback, the cell at each level containing the current playhead position is visually highlighted (brighter fill, border, or slight elevation). In the word panel, the current word is highlighted and scrolled into view.

---

## 5. Decisions Log

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Primary visualization | Icicle diagram + minimap | Preserves timeline, shows hierarchy, width encodes duration |
| 2 | Long-form strategy | Viewport + minimap + adaptive sizing (A + E) | Proven pattern, global context always available |
| 3 | Timestamp resolution | LLM produces text anchors, deterministic post-processing resolves to word-level | LLM can't reliably produce exact ms values; text anchors are verifiable |
| 4 | Exact vs fuzzy matching | Exact substring match first, fuzzy n-gram fallback | Transcript text and word array should be verbatim; fuzzy is defensive only |
| 5 | L2 boundary alignment | Aligned to utterance boundaries | Clean speaker attribution, simpler matching, avoids mid-utterance splits |
| 6 | Cross-topic references | Deferred to post-V1 | Adds complexity (arc diagram hybrid); V1 hierarchy is self-contained |
| 7 | Adaptive cell collapse | Strict per-level (not per-cell) | Avoids broken mixed states; clean level transitions |
| 8 | Word-level view | Word panel on L2 click | Readability and simplicity; no virtualization; icicle stays at 2 LLM levels |
| 9 | Hierarchy depth | 2 LLM levels (Topics + Segments) | Simpler LLM task, more reliable output, works across content types |
| 10 | Video player | HTML5 `<video>` with local files | No iframe restrictions, native events, full control, no external dependencies |
| 11 | Transcript source | Pre-generated, user-provided | Keeps scope to visualization; no transcription pipeline in V1 |

---

## 6. Out of Scope for V1

- Transcription pipeline (Whisper, AssemblyAI, etc.)
- YouTube or external video embed support
- Cross-theme reference visualization (arc diagram overlay)
- Semantic zoom (non-time-linear cell sizing)
- Speaker contribution analytics (Sankey overlay)
- Two-stage navigation for very long content (>3 hours)
- Collaborative features
- Search within transcript
- Export or sharing

---

## 7. Open Questions

- Exact color palette and theme-to-color mapping strategy (categorical palette vs. generated)
- Mobile/touch interaction specifics (pinch-to-zoom behavior, tap vs. long-press)
- Performance targets (max word count, frame rate during playback sync)
- Error handling for LLM output that fails timestamp resolution
- Whether L0 thesis row adds visual value or if it should be text-only above the icicle
- Optimal number of L2 segments per topic (too few = word panel is overwhelming, too many = icicle is cluttered)