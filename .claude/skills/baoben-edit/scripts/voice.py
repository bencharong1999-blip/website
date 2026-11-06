#!/usr/bin/env python3
"""Prepare Ben's iPhone voice recordings: find spoken parts, clean, level.

Usage:
  voice.py report  AUDIO [--noise-db -35] [--min-silence 0.5] [-o report.json]
  voice.py clean   AUDIO -o clean.wav [--mix 0.8] [--no-denoise] [--preview 10]

report: lists speech segments and pauses (ffmpeg silencedetect) plus loudness,
        so takes and retakes of a sentence are easy to find by time.
clean:  high-pass 80 Hz + RNNoise (arnndn, model std.rnnn) + two-pass loudnorm
        to -16 LUFS / -1.5 dBTP. Writes 48 kHz mono WAV and, with --preview,
        an A/B file (original then cleaned) of the first N seconds.
The original file is never modified.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

# Model bundled with the skill (Xiph RNNoise std model, see models/README.md).
MODEL = Path(__file__).resolve().parent.parent / "models" / "std.rnnn"

# Loudness targets Ben chose for every clip.
TARGET_I, TARGET_TP, TARGET_LRA = -16.0, -1.5, 11.0


def run(cmd):
    """Run a command and return its stderr text (ffmpeg writes reports there)."""
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stderr


def duration(path):
    """Return the duration of a media file in seconds."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def loudness(path, af=None):
    """Measure integrated loudness, true peak and LRA with ebur128."""
    chain = (af + "," if af else "") + "ebur128=peak=true"
    err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
               "-af", chain, "-f", "null", "-"])
    summary = err[err.rfind("Summary:"):]
    get = lambda key: float(re.search(key + r":\s+(-?[\d.]+|-inf)", summary)
                            .group(1).replace("-inf", "-999"))
    return {"I_LUFS": get(r"\bI"), "LRA_LU": get("LRA"), "TP_dBTP": get("Peak")}


def silences(path, noise_db, min_sil):
    """Return (start, end) pairs of silence found by ffmpeg silencedetect."""
    err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
               f"silencedetect=n={noise_db}dB:d={min_sil}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    total = duration(path)
    if len(ends) < len(starts):
        ends.append(total)
    return [(max(s, 0.0), e) for s, e in zip(starts, ends)], total


def speech_segments(sil, total):
    """Invert silence ranges into speech ranges covering the whole file."""
    segs, cur = [], 0.0
    for s, e in sil:
        if s - cur > 0.05:
            segs.append((cur, s))
        cur = e
    if total - cur > 0.05:
        segs.append((cur, total))
    return segs


def cmd_report(a):
    """Print and save speech segments, pauses and loudness of one recording."""
    sil, total = silences(a.audio, a.noise_db, a.min_silence)
    segs = speech_segments(sil, total)
    rep = {
        "file": a.audio, "duration_s": round(total, 2),
        "loudness": loudness(a.audio),
        "settings": {"noise_db": a.noise_db, "min_silence_s": a.min_silence},
        "speech": [{"n": i + 1, "start": round(s, 2), "end": round(e, 2),
                    "len": round(e - s, 2)} for i, (s, e) in enumerate(segs)],
        "pauses": [{"start": round(s, 2), "end": round(e, 2)} for s, e in sil],
    }
    Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"{a.audio}: {total:.1f}s, {len(segs)} speech segments, "
          f"{len(sil)} pauses, I={rep['loudness']['I_LUFS']} LUFS -> {a.out}")
    for s in rep["speech"]:
        print(f"  #{s['n']:>2} {s['start']:7.2f} - {s['end']:7.2f}  ({s['len']:.2f}s)")


def clean_chain(mix, denoise):
    """Build the filter chain before loudness normalisation."""
    parts = ["highpass=f=80"]
    if denoise:
        parts.append(f"arnndn=m='{MODEL}':mix={mix}")
    return ",".join(parts)


def cmd_clean(a):
    """Denoise and level one recording with two-pass loudnorm, plus A/B preview."""
    pre = clean_chain(a.mix, not a.no_denoise)
    err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", a.audio, "-af",
               f"{pre},loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
               ":print_format=json", "-f", "null", "-"])
    m = json.loads(err[err.rfind("{"):err.rfind("}") + 1])
    second = (f"{pre},loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
              f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
              f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
              f":offset={m['target_offset']}:linear=true")
    run(["ffmpeg", "-hide_banner", "-y", "-i", a.audio, "-af", second,
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", a.out])
    after = loudness(a.out)
    print(f"{a.out}: I={after['I_LUFS']} LUFS TP={after['TP_dBTP']} dBTP "
          f"LRA={after['LRA_LU']} LU (denoise={'off' if a.no_denoise else a.mix})")
    if a.preview:
        ab = str(Path(a.out).with_name(Path(a.out).stem + "_AB.wav"))
        run(["ffmpeg", "-hide_banner", "-y", "-t", str(a.preview), "-i", a.audio,
             "-t", str(a.preview), "-i", a.out, "-filter_complex",
             "[0:a]aformat=sample_rates=48000:channel_layouts=mono,"
             "loudnorm=I=-16:TP=-1.5[o];[1:a]aformat=channel_layouts=mono[c];"
             "[o][c]concat=n=2:v=0:a=1", "-c:a", "pcm_s16le", ab])
        print(f"A/B preview (original {a.preview}s, then cleaned): {ab}")


def main():
    """Parse arguments and dispatch to report or clean."""
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("audio")
    r.add_argument("--noise-db", type=float, default=-35)
    r.add_argument("--min-silence", type=float, default=0.5)
    r.add_argument("-o", "--out", default="voice_report.json")
    c = sub.add_parser("clean")
    c.add_argument("audio")
    c.add_argument("-o", "--out", required=True)
    c.add_argument("--mix", type=float, default=0.8)
    c.add_argument("--no-denoise", action="store_true")
    c.add_argument("--preview", type=float, default=0)
    a = ap.parse_args()
    cmd_report(a) if a.cmd == "report" else cmd_clean(a)


if __name__ == "__main__":
    main()
