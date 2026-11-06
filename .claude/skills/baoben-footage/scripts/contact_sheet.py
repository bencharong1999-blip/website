#!/usr/bin/env python3
"""Build a timestamped contact sheet from a video using ffmpeg + Pillow.

Usage: contact_sheet.py VIDEO [-n 12] [--start S] [--end E] [--cols 4] [-o sheet.jpg]
Writes the sheet image and a JSON file listing the timestamp of every frame.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


def probe_duration(path):
    """Return the container duration of the video in seconds."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def grab_frame(path, t, dest, width):
    """Extract a single frame at time t (seconds), scaled to the given width."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale={width}:-2", str(dest)],
        check=True,
    )


def fmt(t):
    """Format seconds as MM:SS.s for labels."""
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def main():
    """Parse arguments, sample frames evenly, and tile them with time labels."""
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-n", type=int, default=12)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("-o", "--out", default="contact_sheet.jpg")
    a = ap.parse_args()

    end = a.end if a.end is not None else probe_duration(a.video)
    span = max(end - a.start, 0.001)
    times = [a.start + span * (i + 0.5) / a.n for i in range(a.n)]

    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(times):
            p = Path(tmp) / f"f{i:03d}.jpg"
            grab_frame(a.video, t, p, a.width)
            if p.exists():
                frames.append((t, Image.open(p).convert("RGB")))

    if not frames:
        raise SystemExit("no frames extracted")
    w = max(im.width for _, im in frames)
    h = max(im.height for _, im in frames)
    rows = (len(frames) + a.cols - 1) // a.cols
    sheet = Image.new("RGB", (w * a.cols, h * rows), "black")
    draw = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(frames):
        x, y = (i % a.cols) * w, (i // a.cols) * h
        sheet.paste(im, (x, y))
        label = f"#{i + 1} {fmt(t)}"
        draw.rectangle([x, y, x + 8 * len(label) + 8, y + 18], fill="black")
        draw.text((x + 4, y + 3), label, fill="yellow")
    sheet.save(a.out, quality=85)

    meta = {"video": a.video, "frames": [{"n": i + 1, "t": round(t, 3)}
                                        for i, (t, _) in enumerate(frames)]}
    Path(a.out).with_suffix(".json").write_text(json.dumps(meta, indent=2))
    print(f"{a.out}: {len(frames)} frames, {a.start:.1f}-{end:.1f}s")


if __name__ == "__main__":
    main()
