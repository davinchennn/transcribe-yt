# Implementation Plan: Drop Utterances Column

## Overview

Remove the `utterances` column from the transcripts table and derive utterances on-the-fly from words when needed. This reduces storage by ~30-40% and eliminates redundant data.

## Phase 1: Add Utterance Derivation Logic

### 1.1 Add `derive_utterances()` function to models.py

Create a utility function that groups words into utterances based on:
- Speaker changes
- Pauses exceeding threshold (default 1000ms)

```python
def derive_utterances(words: List[Word], pause_threshold_ms: int = 1000) -> List[Utterance]:
    """Group words into utterances by speaker and pauses."""
```

### 1.2 Add computed property to Transcript model

Make `Transcript.utterances` a property that derives from words if not explicitly set:

```python
@property
def utterances(self) -> List[Utterance]:
    if self._utterances:
        return self._utterances
    return derive_utterances(self.words)
```

## Phase 2: Update Storage Layer

### 2.1 Modify SQLiteStorage.save_transcript()

- Remove utterances serialization
- Only save words to database

### 2.2 Modify SQLiteStorage.get_transcript()

- Don't read utterances column (will be NULL)
- Return Transcript with only words populated
- Utterances will be derived via property access

### 2.3 Database Migration

- Drop `utterances` column from existing table
- Or: Leave column but stop writing to it (simpler, no migration needed)

Recommendation: Leave column in place but stop writing to it. This avoids complex migration and the column will naturally be empty for new records.

## Phase 3: Update Tests

### 3.1 Test derive_utterances()

- Empty words list → empty utterances
- Single word → single utterance
- Same speaker consecutive words → grouped
- Different speakers → separate utterances
- Long pause → new utterance
- No speaker labels → all words in one utterance

### 3.2 Test Transcript.utterances property

- With explicit utterances → returns them
- With only words → derives utterances
- With empty words → empty list

## Files to Modify

1. **packages/core/src/transcripts/models.py**
   - Add `derive_utterances()` function
   - Modify Transcript class to use computed property

2. **packages/core/src/transcripts/storage/sqlite.py**
   - Update `save_transcript()` to skip utterances
   - Update `_row_to_transcript()` to not expect utterances

3. **packages/core/tests/test_models.py** (new or existing)
   - Add tests for derive_utterances()

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Existing data has utterances, new doesn't | Property handles both cases gracefully |
| Performance of deriving on every access | Cache result in instance; words list is small |
| Different derivation than provider | Acceptable - our grouping is consistent |

## Success Criteria

- [ ] New transcripts don't store utterances column data
- [ ] Existing transcripts still work (property derives from words)
- [ ] `transcript.utterances` returns correct groupings
- [ ] Tests pass for derivation logic
