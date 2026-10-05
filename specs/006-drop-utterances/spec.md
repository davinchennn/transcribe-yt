# Feature Specification: Drop Utterances Column

**Feature Branch**: `006-drop-utterances`
**Depends On**: 005-transcript-storage
**Created**: 2026-01-31
**Status**: Complete
**Input**: User description: "Only store words, derive utterances on-the-fly"

## Summary

Remove the `utterances` column from the transcripts table since utterances can always be derived from words. This reduces storage by ~30-40% and eliminates redundant data.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reduced Storage (Priority: P1)

Transcript storage uses less space by not duplicating data.

**Why this priority**: Core optimization - affects all transcripts.

**Independent Test**: Compare database size before/after for same transcript.

**Acceptance Scenarios**:

1. **Given** a new transcription completes, **When** saved to database, **Then** only `words` column is populated (no `utterances`)
2. **Given** existing code requests utterances, **When** retrieved, **Then** utterances are derived from words correctly

---

### User Story 2 - Derive Utterances (Priority: P1)

System derives utterances from words when needed for display.

**Why this priority**: Maintains feature parity - conversation view still works.

**Independent Test**: Retrieve transcript, verify utterances match expected grouping.

**Acceptance Scenarios**:

1. **Given** words with speaker labels, **When** deriving utterances, **Then** consecutive words by same speaker are grouped
2. **Given** a pause > threshold between words, **When** deriving utterances, **Then** a new utterance starts

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST NOT store `utterances` column in database
- **FR-002**: System MUST derive utterances from words on retrieval
- **FR-003**: System MUST handle transcripts with no speaker labels (single utterance)
- **FR-004**: Transcript.utterances property MUST return derived utterances

### Changes

1. **Database schema**: Drop `utterances` column from `transcripts` table
2. **SQLiteStorage.save_transcript()**: Don't save utterances
3. **SQLiteStorage.get_transcript()**: Derive utterances from words
4. **Transcript model**: Add `derive_utterances()` method or compute on access

### Utterance Derivation Logic

```python
def derive_utterances(words: List[Word], pause_threshold_ms: int = 1000) -> List[Utterance]:
    """Group words into utterances by speaker and pauses."""
    if not words:
        return []

    utterances = []
    current_speaker = words[0].speaker
    current_words = [words[0]]

    for word in words[1:]:
        # New utterance if speaker changes or pause > threshold
        pause = word.start - current_words[-1].end
        if word.speaker != current_speaker or pause > pause_threshold_ms:
            utterances.append(Utterance(
                speaker=current_speaker or "SPEAKER",
                text=" ".join(w.text for w in current_words),
                start=current_words[0].start,
                end=current_words[-1].end,
            ))
            current_speaker = word.speaker
            current_words = [word]
        else:
            current_words.append(word)

    # Don't forget last utterance
    if current_words:
        utterances.append(Utterance(...))

    return utterances
```

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Database size reduced by 30%+ for typical transcripts
- **SC-002**: Derived utterances match original provider utterances (within grouping tolerance)
- **SC-003**: No breaking changes to existing API/CLI
