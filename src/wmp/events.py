"""The event contract between the wrist device and the backend."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MAX_CHUNK_B64 = 400_000  # ~5 s of 16 kHz int16 audio is 213 KB base64


class Event(BaseModel):
    event_id: str = Field(min_length=8, max_length=64)
    device_id: str = Field(min_length=1, max_length=64)
    type: Literal["button_down", "audio_chunk", "button_up"]
    capture_id: str = Field(min_length=1, max_length=96)
    ts: float                       # device clock, unix seconds
    seq: int = Field(default=0, ge=0, le=10_000)
    audio_b64: str | None = None    # int16 little-endian PCM, 16 kHz mono
    meta: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _audio_rules(self):
        if self.type == "audio_chunk":
            if not self.audio_b64:
                raise ValueError("audio_chunk needs audio_b64")
            if len(self.audio_b64) > MAX_CHUNK_B64:
                raise ValueError("audio chunk too large")
        elif self.audio_b64:
            raise ValueError(f"{self.type} must not carry audio")
        return self
