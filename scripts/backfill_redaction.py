"""Re-redact stored captures after a privacy upgrade (v1 -> v2), using the eval-only raw transcript log,
and refresh their embeddings. In production raw text would not exist; new captures use v2 directly."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from wmp import db  # noqa: E402
from wmp.embed import embed  # noqa: E402
from wmp.privacy import redact  # noqa: E402

rows = [json.loads(l) for l in open(ROOT / "results/raw_transcripts.jsonl")]
with db.connect() as c:
    for r in rows:
        red, n = redact(r["raw"])
        c.execute("UPDATE captures SET text=%s, pii_spans=%s, embedding=%s WHERE capture_id=%s",
                  (red, n, np.array(embed([red or "(silence)"])[0]), r["capture_id"]))
print(len(rows), "captures re-redacted")
