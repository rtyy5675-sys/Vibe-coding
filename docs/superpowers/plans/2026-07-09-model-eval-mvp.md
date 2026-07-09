# Model Evaluation MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and implement each phase in order.

**Goal:** Build the local fixture-based STT, TTS, and LLM evaluation application defined by `MVP_SPEC.md`.

**Architecture:** Flask exposes upload, task, retry, report, and page routes. Focused `mvp` modules own SQLite persistence, ingestion, task execution, and report generation; generated artifacts remain on disk and SQLite stores paths plus metadata.

**Tech Stack:** Python 3.9, Flask, sqlite3, JiWER, unittest, vanilla HTML/CSS/JavaScript.

---

### Phase 1: FR-001 through FR-006

- [ ] Add failing ingestion and storage tests.
- [ ] Implement strict JSONL/CSV parsing and model-specific validation.
- [ ] Implement SQLite initialization for all six Spec tables.
- [ ] Implement upload persistence, checksums, canonical files, `upload_id`, and `dataset_version`.
- [ ] Add Flask startup, upload API, and upload page.
- [ ] Run phase tests and commit.

### Phase 2: FR-007 through FR-015

- [ ] Add failing task lifecycle and scorer tests.
- [ ] Implement task creation, state transitions, progress, and restart recovery.
- [ ] Implement single-worker fixture execution with item persistence.
- [ ] Reuse STT/TTS scorers and add deterministic LLM rule scoring.
- [ ] Implement failed/incomplete-only retry.
- [ ] Run phase tests and commit.

### Phase 3: FR-016 through FR-020

- [ ] Add failing reporting and page tests.
- [ ] Generate escaped HTML and canonical CSV reports.
- [ ] Add task details, report routes, and recent task list.
- [ ] Ensure report retry never reruns scoring.
- [ ] Run phase tests and commit.

### Phase 4: Acceptance

- [ ] Cover AT-001 through AT-009 with unittest.
- [ ] Add `scripts/smoke_test.py` for AT-010.
- [ ] Run the full unittest suite.
- [ ] Start the service and run the three-model smoke test.
- [ ] Reconcile every MUST requirement against `MVP_SPEC.md`.
- [ ] Update README, commit, and push.
