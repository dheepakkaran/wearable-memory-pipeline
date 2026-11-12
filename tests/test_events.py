import pytest
from pydantic import ValidationError

from wmp.events import Event

BASE = {"event_id": "e" * 16, "device_id": "wrist-01", "capture_id": "c1", "ts": 1.0}


def test_audio_chunk_needs_audio():
    with pytest.raises(ValidationError):
        Event(**BASE, type="audio_chunk")


def test_button_events_cannot_carry_audio():
    with pytest.raises(ValidationError):
        Event(**BASE, type="button_up", audio_b64="AAAA")


def test_oversized_chunk_rejected():
    with pytest.raises(ValidationError):
        Event(**BASE, type="audio_chunk", audio_b64="A" * 500_000)


def test_valid_chunk():
    assert Event(**BASE, type="audio_chunk", seq=2, audio_b64="AAAA").seq == 2
