"""Latency.
  bulk:      transcription time per 30 s capture from the full run (results/raw_transcripts.jsonl)
  quantized: the same 30 captures transcribed with int8 vs float32 weights (same model, same audio)
  realtime:  end-to-end time from button_up to the redacted transcript being stored, with the device
             uploading at real speed (from results/raw_transcripts_realtime.jsonl)"""
import json
import statistics as st
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from wmp.config import CACHE, WHISPER_MODEL  # noqa: E402

pct = lambda xs, p: round(float(np.percentile(xs, p)), 1)


def summarize(path):
    rows = [json.loads(l) for l in open(path)]
    t = [r["transcribe_ms"] for r in rows]
    rtf = [r["transcribe_ms"] / 1000 / r["audio_s"] for r in rows if r["audio_s"] > 1]
    return {"n": len(rows), "transcribe_ms_p50": pct(t, 50), "transcribe_ms_p95": pct(t, 95),
            "realtime_factor_median": round(st.median(rtf), 3),
            "e2e_ms_p50": pct([r["e2e_ms"] for r in rows], 50), "e2e_ms_p95": pct([r["e2e_ms"] for r in rows], 95)}


def quantized(n=30, meeting="ES2008a"):
    from faster_whisper import WhisperModel
    audio, _ = sf.read(ROOT / f"data/raw/{meeting}.wav", dtype="float32")
    clips = [audio[i * 480_000:(i + 1) * 480_000] for i in range(n)]
    out = {}
    for ct in ("int8", "float32"):
        m = WhisperModel(WHISPER_MODEL, device="cpu", compute_type=ct, cpu_threads=6, download_root=str(CACHE / "whisper"))
        m.transcribe(clips[0][:16000], language="en")  # warm up
        ts, texts = [], []
        for c in clips:
            t0 = time.time()
            segs, _ = m.transcribe(c, language="en", beam_size=1, vad_filter=True, condition_on_previous_text=False)
            texts.append(" ".join(s.text.strip() for s in segs))
            ts.append((time.time() - t0) * 1000)
        out[ct] = {"p50_ms": pct(ts, 50), "p95_ms": pct(ts, 95), "mean_ms": round(st.mean(ts), 1), "texts": texts}
        del m
    import jiwer
    sys.path.insert(0, str(ROOT / "eval"))
    from wer import norm
    gold = json.loads((ROOT / f"eval/gold/{meeting}.words.json").read_text())
    refs = [norm(" ".join(w["w"] for w in gold if i * 30 <= w["t"] < (i + 1) * 30)) for i in range(n)]
    keep = [i for i, r in enumerate(refs) if r]
    for ct in out:
        out[ct]["wer"] = round(jiwer.wer([refs[i] for i in keep], [norm(out[ct]["texts"][i]) for i in keep]), 4)
        del out[ct]["texts"]
    out["speedup_mean"] = round(out["float32"]["mean_ms"] / out["int8"]["mean_ms"], 2)
    out["clips"] = f"{n} x 30 s from {meeting}"
    return out


if __name__ == "__main__":
    res = {"model": WHISPER_MODEL, "cpu": "8-core laptop CPU, 6 threads"}
    res["bulk"] = summarize(ROOT / "results/raw_transcripts.jsonl")
    res["bulk"]["note"] = "e2e in bulk mode includes queue wait (all captures uploaded at once): not a latency number"
    rt = ROOT / "results/raw_transcripts_realtime.jsonl"
    if rt.exists():
        res["realtime"] = summarize(rt)
    prev = ROOT / "results/latency.json"
    if "--quant" in sys.argv:
        res["quantized"] = quantized()
    elif prev.exists() and "quantized" in json.loads(prev.read_text()):
        res["quantized"] = json.loads(prev.read_text())["quantized"]
    (ROOT / "results/latency.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
