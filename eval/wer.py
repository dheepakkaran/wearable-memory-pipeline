"""Word error rate of the real-time transcripts vs the AMI human transcript, per 30 s capture window."""
import json
import re
from pathlib import Path

import jiwer

ROOT = Path(__file__).resolve().parent.parent
FILLERS = {"um", "uh", "mm", "hmm", "mm-hmm", "uh-huh", "huh", "ah", "oh", "er", "erm", "mm'kay", "'kay", "hm"}


def norm(s):
    s = s.lower().replace("_", "")
    toks = re.findall(r"[a-z0-9']+(?:-[a-z0-9']+)*", s)
    return " ".join(t for t in toks if t not in FILLERS)


def main(path=ROOT / "results/raw_transcripts.jsonl"):
    rows = [json.loads(l) for l in open(path)]
    gold = {}
    refs, hyps, per = [], [], {}
    for r in rows:
        m = r["meeting_id"]
        if m not in gold:
            gold[m] = json.loads((ROOT / f"eval/gold/{m}.words.json").read_text())
        ref = norm(" ".join(w["w"] for w in gold[m] if r["start_s"] <= w["t"] < r["end_s"]))
        hyp = norm(r["raw"])
        if not ref:
            continue
        refs.append(ref); hyps.append(hyp)
        per.setdefault(m, ([], []))
        per[m][0].append(ref); per[m][1].append(hyp)
    out = {"captures": len(refs), "wer": round(jiwer.wer(refs, hyps), 4),
           "per_meeting": {m: round(jiwer.wer(a, b), 4) for m, (a, b) in sorted(per.items())},
           "model": rows[0]["model"], "compute": rows[0]["compute"],
           "note": "lowercased, punctuation and fillers (um, uh, mm-hmm ...) removed from both sides; "
                   "words cut at 30 s capture borders count against both"}
    (ROOT / "results/wer.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
