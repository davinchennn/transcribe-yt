# Tasks: Drop Utterances Column

## Phase 1: Add Utterance Derivation Logic

- [x] **T001**: Add `derive_utterances()` function to models.py
- [x] **T002**: Modify Transcript class to use `_utterances` internal field (not needed - kept simpler)
- [x] **T003**: Add `utterances` property that derives from words if needed (handled in storage layer)

## Phase 2: Update Storage Layer

- [x] **T004**: Update `save_transcript()` to not save utterances
- [x] **T005**: Update `_row_to_transcript()` to derive utterances from words

## Phase 3: Testing

- [x] **T006**: Test derive_utterances with various scenarios
- [x] **T007**: Test end-to-end: save transcript, retrieve, check utterances
