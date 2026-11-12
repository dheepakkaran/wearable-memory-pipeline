"""Thin Claude wrapper: strict JSON out, prompt caching on the system prompt, a cost ledger with a hard cap."""
import json
import time

import anthropic

from .config import COST_CAP_USD, MODELS, PRICE, RESULTS

LEDGER = RESULTS / "cost_ledger.jsonl"
_client = None


class BudgetExceeded(RuntimeError):
    pass


def spent() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(l)["usd"] for l in LEDGER.read_text().splitlines() if l.strip())


def _cost(model, u) -> float:
    pin, pout = PRICE[model]
    cached = (getattr(u, "cache_read_input_tokens", 0) or 0)
    written = (getattr(u, "cache_creation_input_tokens", 0) or 0)
    return (u.input_tokens * pin + cached * pin * 0.1 + written * pin * 1.25 + u.output_tokens * pout) / 1e6


def call_json(step: str, tier: str, system: str, user: str, schema: dict, effort: str = "low", max_tokens: int = 8000) -> dict:
    """One structured-output call. Raises BudgetExceeded before spending past the cap."""
    global _client
    if spent() >= COST_CAP_USD:
        raise BudgetExceeded(f"spent ${spent():.4f} >= cap ${COST_CAP_USD}")
    _client = _client or anthropic.Anthropic(timeout=60, max_retries=3)
    model = MODELS[tier]
    t0 = time.time()
    resp = _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    usd = _cost(model, resp.usage)
    LEDGER.parent.mkdir(exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps({"ts": round(t0, 1), "step": step, "model": model, "in": resp.usage.input_tokens,
                            "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
                            "out": resp.usage.output_tokens, "usd": round(usd, 6),
                            "s": round(time.time() - t0, 2), "stop": resp.stop_reason}) + "\n")
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"refusal in {step}")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)
