"""hit@3 and MRR@10 on the 20 frozen questions: BM25 keyword baseline vs embedding search vs hybrid."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from wmp import db  # noqa: E402
from wmp.retrieve import METHODS  # noqa: E402


def main():
    qs = [json.loads(l) for l in open(ROOT / "eval/questions.jsonl")]
    out = {}
    with db.connect() as c:
        for name, fn in METHODS.items():
            hits3, rr, rows = 0, 0.0, []
            for q in qs:
                got = [r[0] for r in fn(c, q["q"], 10)]
                rank = next((i + 1 for i, g in enumerate(got) if g in q["gold"]), None)
                hits3 += bool(rank and rank <= 3)
                rr += 1 / rank if rank else 0
                rows.append({"id": q["id"], "rank": rank, "top3": got[:3]})
            out[name] = {"hit@3": round(hits3 / len(qs), 3), "hits": hits3, "n": len(qs),
                         "mrr@10": round(rr / len(qs), 3), "per_question": rows}
    (ROOT / "results/retrieval.json").write_text(json.dumps(out, indent=1))
    print({k: (v["hit@3"], v["mrr@10"]) for k, v in out.items()})


if __name__ == "__main__":
    main()
