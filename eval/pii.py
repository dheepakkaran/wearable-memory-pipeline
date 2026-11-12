"""Privacy checks.
1. Synthetic test: meeting-style sentences with injected names, phone numbers and emails -> share of injected
   values removed by redaction, per entity type.
2. Real leak scan: participant names said aloud in the AMI meetings (from the human transcript introductions)
   searched in every stored capture (whole word, case-insensitive)."""
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from wmp.privacy import redact  # noqa: E402

FIRST = ["Priya", "Marcus", "Elena", "Kwame", "Sofia", "Daniel", "Aisha", "Tomasz", "Hannah", "Diego"]
LAST = ["Raman", "Okafor", "Lindqvist", "Brennan", "Novak", "Haddad", "Castillo", "Fischer", "Moreau", "Tanaka"]
TEMPL = {
    "PERSON": ["so I'll send the draft to {v} before Friday", "{v} said the budget is fine for now",
               "can you check with {v} about the colours", "okay um {v} is going to handle the user study"],
    "PHONE_NUMBER": ["call me back on {v} after the meeting", "my number is {v} if anything breaks",
                     "the supplier line is {v} I think"],
    "EMAIL_ADDRESS": ["just email it to {v} tonight", "send the slides to {v} please",
                      "the contact for the factory is {v}"],
}


def synth(n_per=30, seed=11):
    rnd = random.Random(seed)
    rows = []
    for kind, temps in TEMPL.items():
        for _ in range(n_per):
            f, l = rnd.choice(FIRST), rnd.choice(LAST)
            v = {"PERSON": f"{f} {l}" if rnd.random() < .5 else f,
                 "PHONE_NUMBER": f"({rnd.randint(200, 989)}) {rnd.randint(200, 989)}-{rnd.randint(1000, 9999)}",
                 "EMAIL_ADDRESS": f"{f.lower()}.{l.lower()}@{rnd.choice(['gmail.com', 'outlook.com', 'acme.io'])}"}[kind]
            rows.append((kind, v, rnd.choice(temps).format(v=v)))
    return rows


AMI_NAMES = ["Laura", "David", "Andrew", "Craig", "Rose", "Lindgren", "Iain", "Jessy", "Courtney", "Agnes",
             "Christine", "Shrida", "Daseri", "Alima", "Amina"]


def main():
    res = {"synthetic": {}, "leaks": {}}
    for kind, v, s in synth():
        red, _ = redact(s)
        parts = [p for p in re.split(r"[\s().@-]+", v) if len(p) > 2]
        removed = not any(p in red for p in parts)
        d = res["synthetic"].setdefault(kind, {"n": 0, "removed": 0, "examples_missed": []})
        d["n"] += 1; d["removed"] += removed
        if not removed and len(d["examples_missed"]) < 3:
            d["examples_missed"].append(red)
    for d in res["synthetic"].values():
        d["recall"] = round(d["removed"] / d["n"], 3)
    tot = sum(d["n"] for d in res["synthetic"].values())
    res["synthetic_overall_recall"] = round(sum(d["removed"] for d in res["synthetic"].values()) / tot, 3)

    import psycopg
    from wmp.config import PG_DSN
    with psycopg.connect(PG_DSN) as c:
        rows = c.execute("SELECT capture_id, text, pii_spans FROM captures").fetchall()
    raw = {}
    rp = ROOT / "results/raw_transcripts.jsonl"
    for l in rp.open():
        r = json.loads(l); raw[r["capture_id"]] = r["raw"]
    pat = re.compile(r"\b(" + "|".join(AMI_NAMES) + r")\b", re.I)
    said = sum(1 for t in raw.values() if pat.search(t))
    leaked = [(cid, pat.findall(t)) for cid, t, _ in rows if pat.search(t)]
    res["leaks"] = {"captures_stored": len(rows), "captures_where_asr_heard_a_name": said,
                    "stored_captures_with_a_name_left": len(leaked), "examples": leaked[:5],
                    "spans_redacted_total": sum(r[2] for r in rows),
                    "names_checked": AMI_NAMES}
    (ROOT / "results/pii.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
