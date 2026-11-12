<div align="center">

# Wearable Voice Memory Pipeline

**Press, speak, forget. The backend remembers what you promised.**

The intelligence layer behind a screenless voice wearable, in miniature: a simulated wrist device streams button-press
captures to a FastAPI backend, a real-time path transcribes them locally, a batch path summarizes the day and pulls out
commitments and memories, personal details are redacted before anything is stored, and you can ask it what was said.

[**Project page + live demo →**](https://dheepakkaran.github.io/wearable-memory-pipeline/#demo) · [Results](RESULTS.md) · [What broke](FAILURES.md)

![python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![fastapi](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![whisper](https://img.shields.io/badge/ASR-faster--whisper%20int8-333)
![redis](https://img.shields.io/badge/stream-Redis%20Streams-DC382D?logo=redis&logoColor=white)
![postgres](https://img.shields.io/badge/DB-PostgreSQL%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white)
![claude](https://img.shields.io/badge/LLM-Haiku%20→%20Sonnet%20→%20Opus-D97757)
![tests](https://img.shields.io/badge/tests-12%20passing-22c55e)

<a href="https://dheepakkaran.github.io/wearable-memory-pipeline/#overview"><img src="docs/media/overview.webp" alt="35-second overview: press the button, it writes down what was said, hides names, finds the promises, and answers questions" width="100%"></a>

<sub>35-second overview (silent preview). <a href="https://dheepakkaran.github.io/wearable-memory-pipeline/#overview">Watch it with sound on the project page →</a></sub>

</div>

> **Data:** 8 meetings from the AMI Meeting Corpus (CC BY 4.0), played through a simulated device. There is no real hardware here, and meeting audio is not wrist audio. Independent learning project, not affiliated with any company.

## How it works

```
 wrist device (simulated)          backend                                       storage
 ───────────────────────           ─────────────────────────────────────────     ────────────────────
 button_down                       POST /events   validate (Pydantic)
 audio_chunk × 6 (5 s each)  ──▶   dedupe by event_id (Redis SET NX)       ──▶   Redis: audio buffer
 button_up                         publish capture to Redis Stream                     │
                                                                                       ▼
                        REAL-TIME   worker: faster-whisper int8 (local CPU)
                                    → PII redaction (Presidio, local)
                                    → embedding (bge-small, local)          ──▶   PostgreSQL + pgvector
                                    → raw audio deleted                            (redacted text only)
                                                                                       │
                        BATCH       5-min windows → Haiku (strict JSON + quote)        │
                                    → validator: quote must be verbatim                │
                                    → fail → Sonnet retry                              │
                                    → Opus: final merge per meeting          ──▶   memories / commitments
                                    → Haiku: meeting summary                       / summaries
                                                                                       │
                        APP LAYER   GET /ask (BM25 + vector hybrid)   GET /today (open commitments)
```

**Privacy by design:** speech is transcribed on the machine, audio is deleted after transcription, only redacted
text is stored, and only redacted text ever reaches the LLM.

**Model routing:** the cheap model reads everything, plain code checks it, a mid model retries only what failed,
and the strong model makes only the final decision. Every call goes to a cost ledger with a hard cap.

## Demo

The [project page](https://dheepakkaran.github.io/wearable-memory-pipeline/#demo) replays a real-time run recorded on 2026-11-11 (the last 3 minutes of AMI meeting ES2010a, uploaded by the simulated device at real speed): device events, Redis Stream hand-off, each transcript as stored (redactions marked, with what the recognizer heard), the end-of-day batch calls with their real tokens and cost, and the commitments checked against the human action items. Its search box runs BM25 in the browser over all 247 stored, redacted captures. Rebuild the demo data with `scripts/build_demo.py` after `sim/device.py ES2010a --start 16 --limit 6 --realtime --event-log results/demo_events.jsonl`.

## Results

See [RESULTS.md](RESULTS.md) (generated from `results/*.json`) and [FAILURES.md](FAILURES.md).

## Run it

```bash
uv sync                                   # Python deps
pixi install && scripts/services.sh start # Redis :6390 + PostgreSQL/pgvector :5442 (no Docker, no sudo)
scripts/get_audio.sh ES2002a ES2005a ES2006a ES2008a ES2010a ES2013a IS1008a IS1009a
# AMI annotations: unzip ami_public_manual_1.6.2.zip into data/ami/
python eval/make_gold.py ES2002a ES2005a ES2006a ES2008a ES2010a ES2013a IS1008a IS1009a

PYTHONPATH=src uvicorn wmp.api:app --port 8091 &                 # ingestion + app API
PYTHONPATH=src python sim/device.py ES2002a ... --dup-rate 0.05   # device uploads (5% re-sent)
PYTHONPATH=src python -m wmp.worker --once --eval-raw            # real-time transcription
PYTHONPATH=src python eval/commitments.py                        # batch extraction + scoring (needs ANTHROPIC_API_KEY)
python eval/wer.py; python eval/retrieval.py; python eval/pii.py; python eval/latency.py --quant
python eval/report.py                                            # RESULTS.md
python -m pytest -q                                              # 12 tests
```

Endpoints: `POST /events` · `GET /ask?q=` · `GET /today` · `GET /summary/{meeting_id}` · `GET /healthz`.

Frozen before any run: `eval/questions.jsonl`, `eval/gold/actions.json`, `prompts/*.md` (hashes in `eval/FROZEN.sha256`).

## Limits

Simulated device, no BLE or firmware. Meeting audio from table microphones, not a wrist. 28 human action items
and 20 questions are small test sets. The human action-item list is incomplete, so precision is a lower bound.
`base.en` Whisper on CPU; a larger model would cut the 22.8% WER.
