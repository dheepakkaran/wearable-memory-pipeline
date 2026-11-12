"""Commitment extraction: rule baseline vs Haiku only vs routed (Haiku + validator + Sonnet retry + Opus merge)
vs all-Opus. Scored by a separate judge model (Sonnet) against the AMI human action items.

recall    = gold action items matched by at least one prediction
precision = predictions that match some gold item (a lower bound: the human list is short and misses
            real commitments, so unmatched predictions are not all wrong)
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
from human_captures import human_captures  # noqa: E402
from wmp.batch import db_captures, run_meeting, store  # noqa: E402
from wmp.llm import LEDGER, call_json  # noqa: E402
from wmp.privacy import redact  # noqa: E402

JUDGE = {"type": "object", "additionalProperties": False, "required": ["gold"],
         "properties": {"gold": {"type": "array", "items": {
             "type": "object", "additionalProperties": False, "required": ["gold_id", "matched"],
             "properties": {"gold_id": {"type": "string"}, "matched": {"type": "array", "items": {"type": "string"}}}}}}}
MEETINGS = ["ES2002a", "ES2005a", "ES2006a", "ES2008a", "ES2010a", "ES2013a", "IS1008a", "IS1009a"]


def judge(meeting, gold, preds, tag):
    if not preds:
        return [[] for _ in gold]
    g = "\n".join(f"G{i}: {t}" for i, t in enumerate(gold))
    p = "\n".join(f"P{i}: {c['text']}" + (f" (owner: {c['owner']})" if c.get("owner") else "") for i, c in enumerate(preds))
    res = call_json(f"judge:{tag}:{meeting}", "mid", (ROOT / "prompts/judge_v1.md").read_text(),
                    f"Meeting {meeting}\n\nGold:\n{g}\n\nPredicted:\n{p}", JUDGE)["gold"]
    by = {r["gold_id"]: r["matched"] for r in res}
    return [[m for m in by.get(f"G{i}", []) if m.startswith("P") and m[1:].isdigit() and int(m[1:]) < len(preds)]
            for i in range(len(gold))]


def spend_by_prefix(start_line):
    rows = [json.loads(l) for l in LEDGER.read_text().splitlines()[start_line:]]
    d = defaultdict(float)
    for r in rows:
        d[r["step"].split(":")[0]] += r["usd"]
    return dict(d), rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["rule", "haiku", "routed", "opus"])
    ap.add_argument("--sources", nargs="+", default=["whisper"])
    a = ap.parse_args()
    gold_all = json.loads((ROOT / "eval/gold/actions.json").read_text())
    path = ROOT / "results/commitments.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    for src in a.sources:
        for mode in a.modes:
            key = f"{mode}/{src}"
            start = len(LEDGER.read_text().splitlines()) if LEDGER.exists() else 0
            tot = {"gold": 0, "gold_hit": 0, "pred": 0, "pred_hit": 0, "escalated": 0, "windows": 0, "dropped_invalid": 0}
            per = {}
            for m in MEETINGS:
                caps = db_captures(m) if src == "whisper" else [dict(c, text=redact(c["text"])[0]) for c in human_captures(m)]
                res = run_meeting(m, caps, mode, with_summary=(mode == "routed" and src == "whisper"))
                if mode == "routed" and src == "whisper":
                    store(m, res, "routed")
                gold = gold_all[m]
                matches = judge(m, gold, res["commitments"], key)
                hit_preds = {int(x[1:]) for ms in matches for x in ms}
                tot["gold"] += len(gold); tot["gold_hit"] += sum(bool(ms) for ms in matches)
                tot["pred"] += len(res["commitments"]); tot["pred_hit"] += len(hit_preds)
                for k in ("escalated", "windows", "dropped_invalid"):
                    tot[k] += res["stats"].get(k, 0)
                per[m] = {"gold": gold, "pred": [c["text"] for c in res["commitments"]], "matches": matches,
                          "stats": res["stats"]}
            spend, rows = spend_by_prefix(start)
            pipeline_usd = sum(v for k, v in spend.items() if k != "judge")
            out[key] = {"recall": round(tot["gold_hit"] / tot["gold"], 3),
                        "precision_lower_bound": round(tot["pred_hit"] / tot["pred"], 3) if tot["pred"] else None,
                        **tot, "pipeline_usd": round(pipeline_usd, 4), "judge_usd": round(spend.get("judge", 0), 4),
                        "usd_by_step": {k: round(v, 5) for k, v in spend.items()},
                        "calls_by_model": {mdl: sum(1 for r in rows if r["model"] == mdl and not r["step"].startswith("judge"))
                                           for mdl in sorted({r["model"] for r in rows})},
                        "per_meeting": per}
            path.write_text(json.dumps(out, indent=1))
            print(key, {k: out[key][k] for k in ("recall", "precision_lower_bound", "gold_hit", "gold", "pred",
                                                  "escalated", "pipeline_usd", "judge_usd")})


if __name__ == "__main__":
    main()
