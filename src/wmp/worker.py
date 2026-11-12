"""Real-time path: read finished captures from the Redis stream, transcribe locally with faster-whisper,
redact PII, embed, store. Raw audio is deleted from Redis right after transcription."""
import argparse
import base64
import json
import os
import time

import numpy as np
import redis

from . import db
from .config import CACHE, GROUP, RESULTS, STREAM, WHISPER_COMPUTE, WHISPER_MODEL
from .embed import embed
from .ingest import client
from .privacy import redact


def load_audio(r: redis.Redis, cid: str) -> np.ndarray:
    parts = r.hgetall(f"cap:{cid}:audio")
    pcm = b"".join(base64.b64decode(parts[k]) for k in sorted(parts, key=lambda k: int(k)))
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def run(once: bool, idle_exit_s: float, eval_raw: bool, name: str = "worker-1"):
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type=WHISPER_COMPUTE,
                         cpu_threads=int(os.getenv("WMP_THREADS", "6")), download_root=str(CACHE / "whisper"))
    r = client()
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError:
        pass
    conn = db.connect()
    raw_log = (RESULTS / os.getenv("WMP_RAW_LOG", "raw_transcripts.jsonl")).open("a") if eval_raw else None
    last = time.time()
    done = 0
    while True:
        msgs = r.xreadgroup(GROUP, name, {STREAM: ">"}, count=1, block=1000)
        if not msgs:
            if once and time.time() - last > idle_exit_s:
                break
            continue
        for _, entries in msgs:
            for mid, fields in entries:
                cid = fields[b"capture_id"].decode()
                meta = r.hgetall(f"cap:{cid}")
                info = json.loads(meta.get(b"meta", b"{}"))
                audio = load_audio(r, cid)
                t0 = time.time()
                segs, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True,
                                           condition_on_previous_text=False)
                text = " ".join(s.text.strip() for s in segs).strip()
                tr_ms = (time.time() - t0) * 1000
                red, n_pii = redact(text)
                vec = embed([red or "(silence)"])[0]
                up_ts = float(meta.get(b"up_ts", time.time()))
                e2e_ms = (time.time() - up_ts) * 1000
                conn.execute(
                    """INSERT INTO captures (capture_id, device_id, meeting_id, start_s, end_s, text, pii_spans,
                       transcribe_ms, e2e_ms, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (capture_id) DO NOTHING""",
                    (cid, meta.get(b"device_id", b"?").decode(), info.get("meeting_id", "?"), info.get("start_s", 0),
                     info.get("end_s", 0), red, n_pii, tr_ms, e2e_ms, np.array(vec)))
                if raw_log:
                    raw_log.write(json.dumps({"capture_id": cid, "meeting_id": info.get("meeting_id"),
                                              "start_s": info.get("start_s"), "end_s": info.get("end_s"),
                                              "raw": text, "audio_s": len(audio) / 16000,
                                              "transcribe_ms": tr_ms, "e2e_ms": e2e_ms,
                                              "model": WHISPER_MODEL, "compute": WHISPER_COMPUTE}) + "\n")
                    raw_log.flush()
                r.delete(f"cap:{cid}:audio", f"cap:{cid}")      # privacy: raw audio gone after transcription
                r.xack(STREAM, GROUP, mid)
                done += 1
                last = time.time()
    print(f"{name}: {done} captures transcribed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="exit when the stream has been idle")
    ap.add_argument("--idle", type=float, default=20)
    ap.add_argument("--eval-raw", action="store_true", help="also log raw transcripts for WER (eval only)")
    a = ap.parse_args()
    db.init()
    run(a.once, a.idle, a.eval_raw)
