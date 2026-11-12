"""Ingestion: validate device events, drop duplicates, buffer audio in Redis, publish finished captures to a stream."""
import json

import redis

from .config import REDIS_URL, STREAM
from .events import Event

TTL = 6 * 3600  # buffered audio expires even if a capture never finishes


def client():
    return redis.Redis.from_url(REDIS_URL)


def ingest(r: redis.Redis, events: list[Event]) -> dict:
    stats = {"accepted": 0, "duplicates": 0, "captures_ready": 0}
    for e in events:
        if not r.set(f"seen:{e.event_id}", 1, nx=True, ex=86_400):   # idempotent: retried uploads are safe
            stats["duplicates"] += 1
            continue
        key = f"cap:{e.capture_id}"
        pipe = r.pipeline()
        if e.type == "button_down":
            pipe.hset(key, mapping={"device_id": e.device_id, "down_ts": e.ts, "meta": json.dumps(e.meta)})
        elif e.type == "audio_chunk":
            pipe.hset(f"{key}:audio", e.seq, e.audio_b64)
            pipe.expire(f"{key}:audio", TTL)
        else:  # button_up -> capture is complete, hand it to the real-time worker
            pipe.hset(key, mapping={"up_ts": e.ts, "n_chunks": e.meta.get("n_chunks", 0), "device_id": e.device_id,
                                    "meta": json.dumps(e.meta)})
            pipe.xadd(STREAM, {"capture_id": e.capture_id})
            stats["captures_ready"] += 1
        pipe.expire(key, TTL)
        pipe.execute()
        stats["accepted"] += 1
    return stats
