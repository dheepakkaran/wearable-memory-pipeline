"""Human (AMI) transcript cut into the same 30 s captures the device sends: the ASR-free upper bound."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPTURE_S = 30


def human_captures(meeting):
    ws = json.loads((ROOT / f"eval/gold/{meeting}.words.json").read_text())
    caps = {}
    for w in ws:
        i = int(w["t"] // CAPTURE_S)
        caps.setdefault(i, []).append(w["w"])
    return [{"capture_id": f"{meeting}-{i:03d}", "start_s": i * CAPTURE_S, "text": " ".join(v)} for i, v in sorted(caps.items())]


if __name__ == "__main__":
    import sys
    for c in human_captures(sys.argv[1]):
        print(c["capture_id"], c["text"])
