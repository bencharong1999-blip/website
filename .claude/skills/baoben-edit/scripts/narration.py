#!/usr/bin/env python3
"""Build a narration track from cuts of Ben's real recordings (a paper edit).

Input JSON (list), one entry per phrase, in story order:

    [{"src": "src/IMG_3639-2.m4a", "in": 63.80, "out": 65.10,
      "text": "ตื่นมาอีกที", "highlight": "ตื่นมา", "motion": "pop",
      "gap": 0.15, "section": "hook"}, ...]

    in/out  seconds in the source file (from asr.py timings, padded a little)
    gap     silence after this phrase (seconds, default 0.12)
    text    on-screen caption for this phrase ("" = no caption); \\n breaks lines

Usage:
    narration.py CUTS.json -o voice.wav --captions text/captions.json --timeline timeline.json

Writes a 48 kHz mono WAV (cuts joined with short fades so there are no clicks),
captions.json in the render.py format timed to the new track, and a timeline
listing where each phrase landed. Nothing is re-voiced or generated: every word
is Ben's own recording.
"""
import argparse
import json
import os
import subprocess
import sys

# Output audio format for the edit (matches the delivery mix).
SAMPLE_RATE = 48000

# Short fade at each cut edge (seconds) to avoid clicks between phrases.
EDGE_FADE = 0.03

# Default pause inserted after each phrase when the cut list does not set one.
DEFAULT_GAP = 0.12


def probe_duration(path):
    """Return the duration of an audio file in seconds."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def build(cuts, base, out_wav):
    """Concatenate the cuts with fades and gaps; return per-cut output start/end times."""
    inputs, filters, labels, timeline = [], [], [], []
    t = 0.0
    for i, c in enumerate(cuts):
        src = os.path.join(base, c["src"])
        dur = round(c["out"] - c["in"], 3)
        if dur <= 0:
            raise ValueError(f"cut {i + 1}: out must be after in")
        gap = c.get("gap", DEFAULT_GAP)
        inputs += ["-i", src]
        fade_out = max(0.0, dur - EDGE_FADE)
        filters.append(
            f"[{i}:a]atrim=start={c['in']}:end={c['out']},asetpts=PTS-STARTPTS,"
            f"aresample={SAMPLE_RATE},aformat=channel_layouts=mono,"
            f"afade=t=in:d={EDGE_FADE},afade=t=out:st={fade_out:.3f}:d={EDGE_FADE},"
            f"apad=pad_dur={gap}[a{i}]")
        labels.append(f"[a{i}]")
        timeline.append({"index": i + 1, "section": c.get("section", ""), "start": round(t, 3),
                         "end": round(t + dur, 3), "src": c["src"], "in": c["in"], "out": c["out"],
                         "text": c.get("text", "")})
        t += dur + gap
    graph = ";".join(filters) + ";" + "".join(labels) + f"concat=n={len(cuts)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *inputs,
                    "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le", out_wav],
                   check=True)
    return timeline, probe_duration(out_wav)


def captions_from(timeline, cuts):
    """Turn cut timings into render.py captions (one caption per phrase with text)."""
    caps = []
    for row, c in zip(timeline, cuts):
        if not c.get("text"):
            continue
        caps.append({"start": round(row["start"] + 0.02, 2), "end": round(row["end"] + 0.05, 2),
                     "text": c["text"], "highlight": c.get("highlight", ""),
                     "motion": c.get("motion", "pop")})
    # Never let one caption run into the next.
    for a, b in zip(caps, caps[1:]):
        a["end"] = min(a["end"], round(b["start"] - 0.02, 2))
    return caps


def main():
    """Parse arguments, build the narration and write captions/timeline files."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cuts")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--captions")
    ap.add_argument("--timeline")
    ap.add_argument("--base", default=".", help="folder that cut 'src' paths are relative to")
    args = ap.parse_args()
    with open(args.cuts, encoding="utf-8") as f:
        cuts = json.load(f)
    timeline, total = build(cuts, args.base, args.output)
    if args.captions:
        os.makedirs(os.path.dirname(args.captions) or ".", exist_ok=True)
        with open(args.captions, "w", encoding="utf-8") as f:
            json.dump(captions_from(timeline, cuts), f, ensure_ascii=False, indent=1)
    if args.timeline:
        with open(args.timeline, "w", encoding="utf-8") as f:
            json.dump({"duration": round(total, 3), "cuts": timeline}, f, ensure_ascii=False, indent=1)
    print(json.dumps({"duration": round(total, 3), "cuts": len(cuts)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
