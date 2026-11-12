"""Package a recorded real-time run for the static project page (docs/demo/).
Everything comes from files written during real runs: results/demo_events.jsonl (device timeline),
results/raw_transcripts_demo.jsonl (worker output), the database (stored captures + batch output for the
meeting) and results/cost_ledger.jsonl (the batch calls for this meeting in the routed run)."""
import json
import sys
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from wmp import db  # noqa: E402

MEETING, FIRST, N = "ES2010a", 16, 6
OUT = ROOT / "docs/demo"
OUT.mkdir(parents=True, exist_ok=True)

audio, sr = sf.read(ROOT / f"data/raw/{MEETING}.wav", dtype="float32")
seg = audio[FIRST * 30 * sr:(FIRST + N) * 30 * sr]
sf.write(OUT / f"{MEETING}-{FIRST:03d}.ogg", seg, sr, format="OGG", subtype="OPUS")

ev = [json.loads(l) for l in open(ROOT / "results/demo_events.jsonl")]
tr = [json.loads(l) for l in open(ROOT / "results/raw_transcripts_demo.jsonl")]
t0 = ev[0]["t"]
timeline = {
    "meeting": MEETING, "first": FIRST, "audio": f"demo/{MEETING}-{FIRST:03d}.ogg", "audio_s": len(seg) / sr,
    "events": [{"t": round(e["t"] - t0, 3), "type": e["type"], "capture_id": e["capture_id"], "seq": e["seq"]} for e in ev],
    "stored": [{"t": round(r["t_stored"] - t0, 3), "capture_id": r["capture_id"], "heard": r["raw"], "stored": r["redacted"],
                "pii_spans": r["pii_spans"], "transcribe_ms": round(r["transcribe_ms"]), "e2e_ms": round(r["e2e_ms"])} for r in tr],
}

with db.connect() as c:
    mem = c.execute("SELECT kind, text, owner, due, capture_ids, model FROM memories WHERE meeting_id=%s ORDER BY id",
                    (MEETING,)).fetchall()
    caps = c.execute("SELECT capture_id, meeting_id, start_s, text FROM captures WHERE meeting_id <> 'ES2003a' "
                     "ORDER BY capture_id").fetchall()

ledger = [json.loads(l) for l in open(ROOT / "results/cost_ledger.jsonl")]
end = next(i for i, r in enumerate(ledger) if r["step"] == f"summary:{MEETING}")
calls, i = [ledger[end]], end - 1
while i >= 0 and not ledger[i]["step"].startswith("judge") and MEETING in ledger[i]["step"]:
    calls.insert(0, ledger[i]); i -= 1
com = json.loads((ROOT / "results/commitments.json").read_text())["routed/whisper"]["per_meeting"][MEETING]
timeline["batch"] = {
    "calls": [{"step": r["step"].split(":")[0], "model": r["model"], "in": r["in"] + r.get("cache_read", 0),
               "out": r["out"], "usd": r["usd"], "s": r["s"]} for r in calls],
    "stats": com["stats"], "gold": com["gold"], "matches": com["matches"],
    "commitments": [{"text": m[1], "owner": m[2], "due": m[3], "capture_ids": m[4]} for m in mem if m[0] == "commitment"],
    "memories": [{"text": m[1], "capture_ids": m[4]} for m in mem if m[0] == "memory"],
    "summary": next((m[1] for m in mem if m[0] == "summary"), ""),
}
(OUT / "run.json").write_text(json.dumps(timeline, indent=1))
(OUT / "captures.json").write_text(json.dumps([{"id": c[0], "m": c[1], "s": c[2], "t": c[3]} for c in caps]))
print(len(ev), "events,", len(tr), "stored,", len(calls), "batch calls,", len(caps), "captures in the search index")
print([(r["step"], r["model"], r["usd"]) for r in calls])
