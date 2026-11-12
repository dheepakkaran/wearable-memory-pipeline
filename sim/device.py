"""Simulated wrist device: cuts meeting audio into 30 s button-press captures and uploads them as events
(button_down, 5 s audio_chunk ..., button_up). Can replay events to test idempotent ingestion and can
pace uploads in real time to measure end-to-end latency."""
import argparse
import base64
import random
import time
import uuid
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
SR, CHUNK_S, CAPTURE_S = 16_000, 5, 30


def captures(meeting: str, limit: int | None):
    audio, sr = sf.read(ROOT / f"data/raw/{meeting}.wav", dtype="int16")
    if audio.ndim > 1:
        audio = audio[:, 0]
    assert sr == SR, sr
    n = len(audio) // (SR * CAPTURE_S) + (1 if len(audio) % (SR * CAPTURE_S) > SR * 3 else 0)
    for i in range(n if limit is None else min(n, limit)):
        seg = audio[i * SR * CAPTURE_S:(i + 1) * SR * CAPTURE_S]
        yield i, i * CAPTURE_S, i * CAPTURE_S + len(seg) / SR, seg


def events_for(meeting, i, start_s, end_s, seg, device):
    cid = f"{meeting}-{i:03d}"
    meta = {"meeting_id": meeting, "start_s": start_s, "end_s": end_s}
    ev = lambda t, **kw: {"event_id": uuid.uuid4().hex, "device_id": device, "type": t, "capture_id": cid,
                          "ts": time.time(), **kw}
    chunks = [seg[j:j + SR * CHUNK_S] for j in range(0, len(seg), SR * CHUNK_S)]
    out = [ev("button_down", meta=meta)]
    out += [ev("audio_chunk", seq=k, audio_b64=base64.b64encode(c.astype("<i2").tobytes()).decode()) for k, c in enumerate(chunks)]
    out.append(ev("button_up", meta={**meta, "n_chunks": len(chunks)}))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("meetings", nargs="+")
    ap.add_argument("--api", default="http://127.0.0.1:8091")
    ap.add_argument("--device", default="wrist-01")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dup-rate", type=float, default=0.0, help="share of events re-sent (flaky network)")
    ap.add_argument("--realtime", action="store_true", help="send each chunk when it would exist on a real device")
    a = ap.parse_args()
    rnd = random.Random(7)
    sent = dups = ready = 0
    with httpx.Client(timeout=60) as http:
        for m in a.meetings:
            for i, s, e, seg in captures(m, a.limit):
                evs = events_for(m, i, s, e, seg, a.device)
                batch = []
                for ev in evs:
                    if a.realtime and ev["type"] == "audio_chunk":
                        time.sleep(CHUNK_S * 0.999)
                        ev["ts"] = time.time()
                    if ev["type"] == "button_up":
                        ev["ts"] = time.time()
                    batch.append(ev)
                    if rnd.random() < a.dup_rate:
                        batch.append(dict(ev)); dups += 1
                    if a.realtime:
                        res = http.post(f"{a.api}/events", json=batch).raise_for_status().json(); batch = []
                        ready += res["captures_ready"]
                if batch:
                    res = http.post(f"{a.api}/events", json=batch).raise_for_status().json()
                    ready += res["captures_ready"]
                sent += len(evs)
    print({"events": sent, "replayed_duplicates": dups, "captures_ready": ready})


if __name__ == "__main__":
    main()
