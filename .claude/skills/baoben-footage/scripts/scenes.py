#!/usr/bin/env python3
"""Split footage into shots with PySceneDetect and flag dark or blurry shots.

Usage: scenes.py VIDEO [VIDEO ...] [--threshold 27] [--min-len 0.6]
                 [-o shots.json] [--sheet shots.jpg]

For every shot: start/end/length, mean brightness (0-255) and sharpness
(variance of the Laplacian) of the middle frame, plus flags "dark"/"blurry".
--sheet tiles the middle frame of every shot with file + time labels, so the
whole batch can be reviewed in one image before choosing shots.
Needs: pip install "scenedetect[opencv-headless]" (tested with 0.6.4).
"""
import argparse
import json
from pathlib import Path

import cv2
from PIL import Image, ImageDraw
from scenedetect import ContentDetector, detect, open_video

# Below this mean brightness the middle frame is flagged "dark".
DARK_LEVEL = 50
# Below this Laplacian variance (on a 360px-wide frame) it is flagged "blurry".
BLUR_LEVEL = 60.0


def frame_at(path, t):
    """Return the BGR frame nearest to time t (seconds), or None."""
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def measure(frame):
    """Return (brightness, sharpness) of a frame resized to 360px width."""
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (360, max(1, int(h * 360 / w))))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    return float(gray.mean()), float(cv2.Laplacian(gray, cv2.CV_64F).var())


def shots_for(path, threshold, min_len):
    """Detect shots in one video; a video with no cut is one shot."""
    video = open_video(str(path))
    fps = video.frame_rate
    scenes = detect(str(path), ContentDetector(
        threshold=threshold, min_scene_len=max(1, int(min_len * fps))))
    if not scenes:
        dur = video.duration.get_seconds()
        ranges = [(0.0, dur)]
    else:
        ranges = [(s.get_seconds(), e.get_seconds()) for s, e in scenes]
    out = []
    for i, (s, e) in enumerate(ranges):
        mid = (s + e) / 2
        frame = frame_at(path, mid)
        bright, sharp = measure(frame) if frame is not None else (None, None)
        flags = []
        if bright is not None and bright < DARK_LEVEL:
            flags.append("dark")
        if sharp is not None and sharp < BLUR_LEVEL:
            flags.append("blurry")
        out.append({"file": str(path), "n": i + 1, "start": round(s, 2),
                    "end": round(e, 2), "len": round(e - s, 2),
                    "mid": round(mid, 2),
                    "brightness": None if bright is None else round(bright, 1),
                    "sharpness": None if sharp is None else round(sharp, 1),
                    "flags": flags})
    return out


def make_sheet(shots, dest, cols=4, width=270):
    """Tile the middle frame of each shot with a file/time/flag label."""
    tiles = []
    for s in shots:
        frame = frame_at(s["file"], s["mid"])
        if frame is None:
            continue
        im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        im = im.resize((width, max(1, int(im.height * width / im.width))))
        tiles.append((s, im))
    if not tiles:
        return
    w = width
    h = max(im.height for _, im in tiles)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, h * rows), "black")
    draw = ImageDraw.Draw(sheet)
    for i, (s, im) in enumerate(tiles):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im, (x, y))
        label = f"{Path(s['file']).stem[:14]} #{s['n']} {s['start']:.1f}-{s['end']:.1f}"
        if s["flags"]:
            label += " " + ",".join(s["flags"])
        draw.rectangle([x, y, x + 7 * len(label) + 6, y + 16], fill="black")
        draw.text((x + 3, y + 2), label, fill="yellow")
    sheet.save(dest, quality=85)


def main():
    """Detect shots in all given videos, write JSON, optionally a sheet."""
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--threshold", type=float, default=27.0)
    ap.add_argument("--min-len", type=float, default=0.6)
    ap.add_argument("-o", "--out", default="shots.json")
    ap.add_argument("--sheet")
    a = ap.parse_args()
    shots = []
    for v in a.videos:
        found = shots_for(v, a.threshold, a.min_len)
        shots.extend(found)
        flagged = sum(1 for s in found if s["flags"])
        print(f"{v}: {len(found)} shots ({flagged} flagged)")
    Path(a.out).write_text(json.dumps(shots, ensure_ascii=False, indent=2))
    if a.sheet:
        make_sheet(shots, a.sheet)
        print(f"sheet: {a.sheet}")
    print(f"{len(shots)} shots -> {a.out}")


if __name__ == "__main__":
    main()
