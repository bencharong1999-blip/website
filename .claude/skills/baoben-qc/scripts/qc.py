#!/usr/bin/env python3
"""Technical QC for a delivery MP4: format, loudness, black frames, full decode.

Usage: qc.py VIDEO [--expect-fps 60] [--width 1080] [--height 1920] [--json out.json]
Exit code 1 if any check FAILs.
"""
import argparse
import json
import re
import subprocess
import sys

# Loudness targets agreed with Ben: integrated around -16 LUFS, true peak <= -1.5 dBTP.
TARGET_LUFS = -16.0
LUFS_TOLERANCE = 1.5
MAX_TRUE_PEAK = -1.0


def run(cmd):
    """Run a command and return (returncode, stdout, stderr)."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def probe(path):
    """Return ffprobe JSON for the file's format and streams."""
    _, out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                     "-of", "json", path])
    return json.loads(out)


def loudness(path):
    """Measure integrated loudness, LRA and true peak with the ebur128 filter."""
    _, _, err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                     "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = err[err.rfind("Summary:"):]

    def grab(label):
        """Pull the numeric value following a label in the ebur128 summary."""
        m = re.search(label + r":\s+(-?[\d.]+|-inf)", summary)
        return float(m.group(1)) if m and m.group(1) != "-inf" else None

    return {"I": grab("I"), "LRA": grab("LRA"), "TP": grab("Peak")}


def black_and_decode(path):
    """Decode the whole file, collecting blackdetect intervals and decode errors."""
    _, _, err = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", path,
                     "-vf", "blackdetect=d=0.5:pic_th=0.98", "-f", "null", "-"])
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)
    errors = [ln for ln in err.splitlines()
              if re.search(r"error|corrupt|invalid", ln, re.I)]
    return [(float(a), float(b)) for a, b in blacks], errors


def main():
    """Run all checks and print a PASS/WARN/FAIL table."""
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--expect-fps", type=float, default=60)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--json")
    a = ap.parse_args()

    info = probe(a.video)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    checks = []

    def add(name, status, detail):
        """Record one check result."""
        checks.append({"check": name, "status": status, "detail": detail})

    dur = float(info["format"].get("duration", 0))
    add("duration", "INFO", f"{dur:.2f}s, {int(info['format'].get('size', 0))} bytes")
    if v is None:
        add("video", "FAIL", "no video stream")
    else:
        size_ok = (v["width"], v["height"]) == (a.width, a.height)
        add("resolution", "PASS" if size_ok else "WARN", f"{v['width']}x{v['height']}")
        num, den = (int(x) for x in v["avg_frame_rate"].split("/"))
        fps = num / den if den else 0
        add("fps", "PASS" if abs(fps - a.expect_fps) < 0.1 else "WARN", f"{fps:.2f}")
        add("video codec", "PASS" if v["codec_name"] == "h264" else "WARN",
            f"{v['codec_name']} {v.get('pix_fmt')} {v.get('color_space', '?')}")
    if au is None:
        add("audio", "FAIL", "no audio stream")
    else:
        add("audio codec", "PASS" if au["codec_name"] == "aac" else "WARN",
            f"{au['codec_name']} {au.get('sample_rate')} Hz {au.get('channels')}ch")
        ld = loudness(a.video)
        i_ok = ld["I"] is not None and abs(ld["I"] - TARGET_LUFS) <= LUFS_TOLERANCE
        add("loudness", "PASS" if i_ok else "WARN", f"{ld['I']} LUFS, LRA {ld['LRA']} LU")
        tp_ok = ld["TP"] is not None and ld["TP"] <= MAX_TRUE_PEAK
        add("true peak", "PASS" if tp_ok else "FAIL", f"{ld['TP']} dBTP")
    blacks, errors = black_and_decode(a.video)
    add("black frames", "PASS" if not blacks else "WARN",
        ", ".join(f"{s:.1f}-{e:.1f}s" for s, e in blacks) or "none >=0.5s")
    add("full decode", "PASS" if not errors else "FAIL",
        f"{len(errors)} error lines" + (f": {errors[0][:120]}" if errors else ""))

    for c in checks:
        print(f"{c['status']:5} {c['check']:13} {c['detail']}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"video": a.video, "checks": checks}, f, indent=2, ensure_ascii=False)
    sys.exit(1 if any(c["status"] == "FAIL" for c in checks) else 0)


if __name__ == "__main__":
    main()
