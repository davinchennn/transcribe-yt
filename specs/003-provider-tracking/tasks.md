# Tasks: Provider Tracking

**Input**: Design documents from `/specs/003-provider-tracking/`

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Model Update

- [ ] T001 Add `provider: Optional[str] = None` field to Job dataclass in src/transcripts/models.py
- [ ] T002 Update `Job.to_dict()` to include provider field in src/transcripts/models.py
- [ ] T003 Update `Job.from_dict()` to read provider field (with None default for legacy) in src/transcripts/models.py

---

## Phase 2: Processor Integration

- [ ] T004 [US1] Update `TranscriptProcessor.process_video()` to set `job.provider = self.provider` after job creation in src/transcripts/processor.py

---

## Phase 3: CLI Display

- [ ] T005 [US1] Update `_show_status()` to add Provider column to table header in src/transcripts/cli/main.py
- [ ] T006 [US1] Update `_show_status()` to display provider (or "-" if None) for each job in src/transcripts/cli/main.py

---

## Dependencies

- T001 → T002, T003 (model field before serialization)
- T003 → T004 (deserialization before processor uses it)
- T004 → T005, T006 (data populated before display)

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| Model | 3 | Add provider field |
| Processor | 1 | Set provider on job |
| CLI | 2 | Display in status |
| **Total** | **6** | |
