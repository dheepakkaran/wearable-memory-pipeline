"""Build the answer key from AMI human annotations (run once, before any model run).

Outputs
  eval/gold/<meeting>.words.json   human words with times, all speakers merged (WER reference + question anchors)
  eval/gold/actions.json           human-written action items per meeting (commitment answer key)
"""
import json, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AMI = ROOT / "data/ami"
OUT = ROOT / "eval/gold"
NS = "{http://nite.sourceforge.net/}"


def words(meeting):
    rows = []
    for f in sorted((AMI / "words").glob(f"{meeting}.*.words.xml")):
        spk = f.name.split(".")[1]
        for w in ET.parse(f).getroot():
            if w.tag != "w" or w.get("punc") == "true" or not w.get("starttime"):
                continue
            rows.append({"t": float(w.get("starttime")), "e": float(w.get("endtime") or w.get("starttime")), "spk": spk, "w": w.text or ""})
    return sorted(rows, key=lambda r: r["t"])


def actions(meeting):
    root = ET.parse(AMI / "abstractive" / f"{meeting}.abssumm.xml").getroot()
    out = []
    for block in root:
        if block.tag == "actions":
            out += [s.text.strip() for s in block if s.tag == "sentence" and s.text]
    return out


if __name__ == "__main__":
    meetings = sys.argv[1:] or ["ES2002a", "ES2003a", "ES2004a", "ES2005a"]
    OUT.mkdir(parents=True, exist_ok=True)
    gold = {}
    for m in meetings:
        ws = words(m)
        (OUT / f"{m}.words.json").write_text(json.dumps(ws))
        gold[m] = actions(m)
        print(m, len(ws), "words,", len(gold[m]), "action items")
    (OUT / "actions.json").write_text(json.dumps(gold, indent=1))
