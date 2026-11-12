"""Batch path (end of day): summary + memory + commitment extraction over the redacted captures.

Routing harness (mode "routed"):
  1. cheap model (Haiku) reads each 5-minute window and returns strict JSON items with an evidence quote
  2. deterministic validator: the quote must appear word for word in the cited capture, ids must exist
  3. a window that fails validation is re-run once on the mid model (Sonnet); items still failing are dropped
  4. strong model (Opus) makes the final decision per meeting: merge duplicates, drop non-commitments
Other modes exist only for the comparison: "rule" (regex, no LLM), "haiku" (step 1 only), "opus" (Opus everywhere).
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np

from . import db
from .config import ROOT
from .embed import embed
from .llm import call_json

PROMPTS = ROOT / "prompts"
WINDOW = 10  # captures per window (~5 minutes)

ITEM = {"type": "object", "additionalProperties": False,
        "required": ["kind", "text", "owner", "due", "evidence_quote", "capture_id"],
        "properties": {"kind": {"type": "string", "enum": ["commitment", "memory"]}, "text": {"type": "string"},
                       "owner": {"type": "string"}, "due": {"type": "string"},
                       "evidence_quote": {"type": "string"}, "capture_id": {"type": "string"}}}
EXTRACT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"],
                  "properties": {"items": {"type": "array", "items": ITEM}}}
MERGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["commitments"],
                "properties": {"commitments": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["text", "owner", "due", "source_ids"],
                    "properties": {"text": {"type": "string"}, "owner": {"type": "string"}, "due": {"type": "string"},
                                   "source_ids": {"type": "array", "items": {"type": "string"}}}}}}}
SUMMARY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary"],
                  "properties": {"summary": {"type": "string"}}}

_norm = lambda s: " ".join(re.findall(r"[a-z0-9<>]+", s.lower()))
COMMIT_RE = re.compile(r"\b(i will|i'll|we will|we'll|you will|you'll|going to|gonna|need to|have to|should|"
                       r"is to|are to|let's|next meeting)\b", re.I)


def prompt(name):
    return (PROMPTS / f"{name}_v1.md").read_text()


def render(caps):
    return "\n".join(f"[{c['capture_id']}] {c['text']}" for c in caps)


def validate(items, caps):
    by_id = {c["capture_id"]: _norm(c["text"]) for c in caps}
    good, bad = [], []
    for it in items:
        q = _norm(it["evidence_quote"])
        ok = (it["capture_id"] in by_id and 3 <= len(q.split()) <= 30 and q in by_id[it["capture_id"]]
              and 5 <= len(it["text"]) <= 300)
        (good if ok else bad).append(it)
    return good, bad


def extract_window(caps, mode, stats, tag):
    tier = {"haiku": "cheap", "routed": "cheap", "opus": "strong"}[mode]
    items = call_json(f"extract:{tag}", tier, prompt("extract"), render(caps), EXTRACT_SCHEMA)["items"]
    if mode == "haiku":
        return items
    good, bad = validate(items, caps)
    stats["windows"] += 1
    if bad and mode == "routed":
        stats["escalated"] += 1
        retry = call_json(f"extract-retry:{tag}", "mid", prompt("extract"), render(caps), EXTRACT_SCHEMA)["items"]
        good, bad = validate(retry, caps)
    stats["dropped_invalid"] += len(bad)
    return good


def rule_extract(caps):
    out = []
    for c in caps:
        for s in re.split(r"(?<=[.?!])\s+", c["text"]):
            if COMMIT_RE.search(s) and not s.strip().endswith("?") and len(s.split()) >= 4:
                out.append({"kind": "commitment", "text": s.strip(), "owner": "", "due": "",
                            "evidence_quote": s.strip(), "capture_id": c["capture_id"]})
    return out


def merge(meeting, cands, tier, stats):
    if not cands:
        return []
    listing = "\n".join(f"[{i}] owner={c['owner'] or '?'} due={c['due'] or '?'} | {c['text']} "
                        f"(quote: \"{c['evidence_quote']}\")" for i, c in enumerate(cands))
    res = call_json(f"merge:{meeting}", tier, prompt("merge"), f"Meeting {meeting} candidates:\n{listing}",
                    MERGE_SCHEMA, effort="medium" if tier == "strong" else "low")["commitments"]
    valid = {str(i) for i in range(len(cands))}
    out = []
    for m in res:
        ids = [i.strip("[]") for i in m["source_ids"]]
        if not ids or not set(ids) <= valid:
            stats["merge_bad_ids"] += 1
            continue
        caps = sorted({cands[int(i)]["capture_id"] for i in ids})
        out.append({"kind": "commitment", "text": m["text"], "owner": m["owner"], "due": m["due"],
                    "evidence": cands[int(ids[0])]["evidence_quote"], "capture_ids": caps})
    return out


def run_meeting(meeting, caps, mode, with_summary=False):
    stats = {"windows": 0, "escalated": 0, "dropped_invalid": 0, "merge_bad_ids": 0}
    caps = sorted(caps, key=lambda c: c["start_s"])
    if mode == "rule":
        cands = rule_extract(caps)
        return {"commitments": [dict(c, capture_ids=[c["capture_id"]]) for c in cands], "memories": [],
                "stats": stats}
    items = []
    for w in range(0, len(caps), WINDOW):
        items += extract_window(caps[w:w + WINDOW], mode, stats, f"{meeting}:{w // WINDOW}")
    cands = [i for i in items if i["kind"] == "commitment"]
    mems = [dict(i, capture_ids=[i["capture_id"]]) for i in items if i["kind"] == "memory"]
    if mode == "haiku":   # no validator, no strong-model decision: exact-text dedupe only
        seen, commits = set(), []
        for c in cands:
            if _norm(c["text"]) not in seen:
                seen.add(_norm(c["text"])); commits.append(dict(c, capture_ids=[c["capture_id"]]))
    else:
        commits = merge(meeting, cands, "strong", stats)
    stats["candidates"] = len(cands)
    out = {"commitments": commits, "memories": mems, "stats": stats}
    if with_summary:
        out["summary"] = call_json(f"summary:{meeting}", "cheap", prompt("summary"), render(caps),
                                   SUMMARY_SCHEMA)["summary"]
    return out


def store(meeting, res, model_tag):
    rows = [("commitment", c) for c in res["commitments"]] + [("memory", m) for m in res["memories"]]
    if res.get("summary"):
        rows.append(("summary", {"text": res["summary"], "owner": "", "due": "", "capture_ids": []}))
    vecs = embed([r[1]["text"] for r in rows]) if rows else []
    with db.connect() as c:
        c.execute("DELETE FROM memories WHERE meeting_id=%s", (meeting,))
        for (kind, r), v in zip(rows, vecs):
            c.execute("INSERT INTO memories (meeting_id, kind, text, owner, due, evidence, capture_ids, model, embedding)"
                      " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (meeting, kind, r["text"], r.get("owner"), r.get("due"),
                       r.get("evidence") or r.get("evidence_quote"), r["capture_ids"], model_tag, np.array(v)))


def db_captures(meeting):
    with db.connect() as c:
        rows = c.execute("SELECT capture_id, start_s, text FROM captures WHERE meeting_id=%s", (meeting,)).fetchall()
    return [{"capture_id": r[0], "start_s": r[1], "text": r[2]} for r in rows]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("meetings", nargs="+")
    a = ap.parse_args()
    for m in a.meetings:
        res = run_meeting(m, db_captures(m), "routed", with_summary=True)
        store(m, res, "routed")
        print(m, len(res["commitments"]), "commitments,", len(res["memories"]), "memories", res["stats"])
