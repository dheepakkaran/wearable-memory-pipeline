import uuid

import pytest
import redis

from wmp.events import Event
from wmp.ingest import ingest


@pytest.fixture
def r():
    c = redis.Redis(port=6390, db=15)
    try:
        c.ping()
    except redis.ConnectionError:
        pytest.skip("redis not running (scripts/services.sh start)")
    c.flushdb()
    yield c
    c.flushdb()


def evs(cid):
    mk = lambda t, **k: Event(event_id=uuid.uuid4().hex, device_id="d", type=t, capture_id=cid, ts=1.0, **k)
    return [mk("button_down"), mk("audio_chunk", seq=0, audio_b64="AAAA"), mk("button_up", meta={"n_chunks": 1})]


def test_duplicates_are_dropped_and_capture_published_once(r):
    batch = evs("cap-x")
    first = ingest(r, batch)
    again = ingest(r, batch)          # flaky network: the device re-sends everything
    assert first == {"accepted": 3, "duplicates": 0, "captures_ready": 1}
    assert again == {"accepted": 0, "duplicates": 3, "captures_ready": 0}
    assert r.xlen("wearable:captures") == 1
    assert r.hget("cap:cap-x:audio", 0) == b"AAAA"
