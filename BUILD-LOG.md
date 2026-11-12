# Build log

2026-11-11, one session.

Done
- Device simulator → FastAPI `/events` (Pydantic validation, event-id dedupe) → Redis buffer + Redis Stream
- Real-time worker: faster-whisper `base.en` int8 on CPU → Presidio redaction → bge-small embedding → PostgreSQL + pgvector; raw audio deleted after transcription
- Batch: Haiku extraction with strict JSON + verbatim-quote validator → Sonnet retry → Opus merge; Haiku summaries
- App layer: `/ask` (BM25 / vector / hybrid), `/today`, `/summary/{meeting}`
- Evals: WER, latency (bulk, real-time, int8 vs float32), privacy (synthetic + real leak scan), retrieval (20 frozen questions), commitments (4 setups × 2 transcript sources, Sonnet judge)
- 12 pytest tests; services from pixi (no Docker)
- Privacy v1 → v2 after measuring v1 (see FAILURES.md)

Spend: $0.98 of a $1.00 hard cap (results/cost_ledger.jsonl). One run hung on an API call; a 60 s timeout was added and it was resumed.

Remaining
- Route role-assignment windows to the stronger model (recall gap vs Opus everywhere)
- Sonnet instead of Opus for the merge, measured
- Device contact list for name redaction
- Larger Whisper model for captures with numbers
