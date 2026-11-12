"""One place for paths, ports, model ids and prices."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

RESULTS = ROOT / "results"
CACHE = ROOT / ".cache"
PG_DSN = os.getenv("WMP_PG", "host=localhost port=5442 user=wmp dbname=wmp")
REDIS_URL = os.getenv("WMP_REDIS", "redis://localhost:6390/0")
STREAM = "wearable:captures"          # one entry per finished capture (button_up)
GROUP = "transcribers"

SAMPLE_RATE = 16_000
CHUNK_S = 5                            # device sends 5 s audio chunks
CAPTURE_S = 30                         # one button press = one 30 s capture in the simulator

WHISPER_MODEL = os.getenv("WMP_WHISPER", "base.en")
WHISPER_COMPUTE = os.getenv("WMP_COMPUTE", "int8")
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384

# Model routing: cheap model does the bulk reading, strong model only makes the final call.
MODELS = {"cheap": "claude-haiku-5-5", "mid": "claude-sonnet-5-5", "strong": "claude-opus-5-5"}
PRICE = {  # USD per 1M tokens (input, output), Anthropic list prices 2026-11
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
COST_CAP_USD = float(os.getenv("WMP_COST_CAP", "0.20"))
