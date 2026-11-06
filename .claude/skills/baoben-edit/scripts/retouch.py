#!/usr/bin/env python3
"""Face-only skin retouch + gentle grade for Ben's talking-head clips.

Pipeline (one pass, no stacked filters):
  ffmpeg decode (BT.709 -> BGR) -> per-frame face detection (OpenCV YuNet)
  -> skin mask inside the face (minus eyes / mouth) -> low-frequency skin
  smoothing + small face brightness/warmth lift -> ffmpeg encode with one
  global grade filter (BGR -> BT.709).

Smoothing is computed on a copy of the face scaled to a fixed width
(`work_face_px`), so the look is the same on a 540p proxy and on the
1080p original. Only the low-frequency difference is added back, so pores,
stubble, brows and eyelashes keep their full-resolution detail.

Usage:
  python3 retouch.py IN.mp4 OUT.mp4 --params retouch.json [--ss 3 --t 8]
         [--mask-debug mask.mp4] [--report report.json]

Needs: ffmpeg, numpy, opencv-python-headless >= 4.8 (FaceDetectorYN),
and the YuNet model (see --model).
"""

import argparse
import json
import os
import subprocess
import sys

import cv2
import numpy as np

# Folder of the bundled YuNet model (skill's models/ directory).
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")

# Default parameters. Values chosen on EP03 p001 proxy (6 Nov 2026) and
# meant to be overridden from a params JSON once Ben has reviewed the look.
DEFAULTS = {
    "version": 1,
    "model": os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx"),
    "detect_width": 360,
    "score_threshold": 0.6,
    "smooth_alpha": 0.5,
    "hold_seconds": 0.5,
    "work_face_px": 160,
    "smooth": {"strength": 0.6, "sigma_color": 22, "sigma_space": 7},
    "face_lift": {"brightness": 0.04, "warmth": 3.0},
    "skin": {"cr": [133, 178], "cb": [75, 130], "soft": 8},
    "protect": {"eye_radius": 0.16, "mouth_w": 0.75, "mouth_h": 0.30},
    "grade": "eq=gamma=1.04:contrast=1.02:saturation=1.05",
    "x264": ["-preset", "medium", "-crf", "18"],
}


def load_params(path):
    """Merge a params JSON (may be a `retouch` sub-block) over DEFAULTS."""
    params = json.loads(json.dumps(DEFAULTS))
    if not path:
        return params
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data = data.get("retouch", data)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(params.get(key), dict):
            params[key].update(value)
        else:
            params[key] = value
    return params


def probe(path):
    """Return (width, height, fps, has_audio) after ffmpeg autorotation."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,avg_frame_rate:stream_side_data=rotation",
         "-of", "json", path], capture_output=True, text=True, check=True)
    streams = json.loads(out.stdout)["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    width, height = video["width"], video["height"]
    rotation = 0
    for side in video.get("side_data_list", []):
        rotation = int(side.get("rotation", 0))
    if abs(rotation) in (90, 270):
        width, height = height, width
    num, den = video["avg_frame_rate"].split("/")
    fps = float(num) / float(den)
    has_audio = any(s["codec_type"] == "audio" for s in streams)
    return width, height, fps, has_audio


def smoothstep(x, lo, hi):
    """Soft 0..1 ramp between lo and hi (array-friendly)."""
    t = np.clip((x - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class FaceTracker:
    """YuNet detection on a downscaled frame with EMA smoothing and hold."""

    def __init__(self, params, width, height, fps):
        self.scale = params["detect_width"] / float(width)
        size = (params["detect_width"], int(round(height * self.scale)))
        self.det = cv2.FaceDetectorYN.create(
            params["model"], "", size, params["score_threshold"])
        self.size = size
        self.alpha = params["smooth_alpha"]
        self.hold = max(1, int(round(params["hold_seconds"] * fps)))
        self.state = None
        self.missing = 0
        self.frames = 0
        self.hits = 0

    def update(self, frame):
        """Return (face vector [x,y,w,h,10 landmarks] in full-res px, weight)."""
        self.frames += 1
        small = cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA)
        _, faces = self.det.detect(small)
        if faces is not None and len(faces):
            best = max(faces, key=lambda f: f[2] * f[3])
            vec = best[:14].astype(np.float64) / self.scale
            self.hits += 1
            self.missing = 0
            if self.state is None:
                self.state = vec
            else:
                self.state = self.alpha * vec + (1 - self.alpha) * self.state
            return self.state, 1.0
        self.missing += 1
        if self.state is None or self.missing > self.hold:
            return None, 0.0
        return self.state, 1.0 - self.missing / float(self.hold + 1)


def build_mask(roi, face, ox, oy, params):
    """Skin mask (float 0..1) for the ROI: face ellipse x skin colour - eyes/mouth."""
    h, w = roi.shape[:2]
    x, y, fw, fh = face[:4]
    cx, cy = x + fw / 2 - ox, y + fh / 2 - oy
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ell = ((xx - cx) / (fw * 0.58)) ** 2 + ((yy - cy + fh * 0.05) / (fh * 0.72)) ** 2
    mask = 1.0 - smoothstep(ell, 0.75, 1.0)

    ycc = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    s = params["skin"]
    soft = s["soft"]
    cr, cb = ycc[..., 1], ycc[..., 2]
    skin = (smoothstep(cr, s["cr"][0] - soft, s["cr"][0] + soft)
            * (1 - smoothstep(cr, s["cr"][1] - soft, s["cr"][1] + soft))
            * smoothstep(cb, s["cb"][0] - soft, s["cb"][0] + soft)
            * (1 - smoothstep(cb, s["cb"][1] - soft, s["cb"][1] + soft)))
    mask *= skin

    p = params["protect"]
    lm = face[4:14].reshape(5, 2) - (ox, oy)  # r-eye, l-eye, nose, r-mouth, l-mouth
    for ex, ey in lm[:2]:
        r = fw * p["eye_radius"]
        d = ((xx - ex) / r) ** 2 + ((yy - ey) / (r * 0.75)) ** 2
        mask *= smoothstep(d, 0.6, 1.0)
    mx, my = (lm[3] + lm[4]) / 2
    mw = max(np.linalg.norm(lm[4] - lm[3]), fw * 0.2) * (0.5 + p["mouth_w"])
    d = ((xx - mx) / (mw / 2)) ** 2 + ((yy - my) / (fh * p["mouth_h"] / 2)) ** 2
    mask *= smoothstep(d, 0.6, 1.0)

    feather = max(1.0, fw * 0.03)
    return cv2.GaussianBlur(mask, (0, 0), feather)


def retouch_frame(frame, face, weight, params):
    """Apply face-only smoothing + lift in place; return (frame, mask or None)."""
    if face is None or weight <= 0:
        return frame, None
    H, W = frame.shape[:2]
    x, y, fw, fh = face[:4]
    x0 = int(max(0, x - fw * 0.35)); x1 = int(min(W, x + fw * 1.35))
    y0 = int(max(0, y - fh * 0.45)); y1 = int(min(H, y + fh * 1.25))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return frame, None
    roi = frame[y0:y1, x0:x1]
    mask = build_mask(roi, face, x0, y0, params) * weight

    # Low-frequency smoothing on a fixed-size copy (resolution independent).
    k = params["work_face_px"] / float(fw)
    small = cv2.resize(roi, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    sm = params["smooth"]
    smooth = cv2.bilateralFilter(small, 0, sm["sigma_color"], sm["sigma_space"])
    delta = smooth.astype(np.float32) - small.astype(np.float32)
    delta = cv2.resize(delta, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_CUBIC)

    out = roi.astype(np.float32) + delta * (sm["strength"] * mask)[..., None]
    lift = params["face_lift"]
    out += (255.0 - out) * (lift["brightness"] * mask)[..., None]
    out[..., 2] += lift["warmth"] * mask
    out[..., 0] -= lift["warmth"] * mask
    frame[y0:y1, x0:x1] = np.clip(out, 0, 255).astype(np.uint8)

    full = np.zeros((H, W), np.float32)
    full[y0:y1, x0:x1] = mask
    return frame, full


def main():
    """CLI entry: decode, retouch frame by frame, encode with audio."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--params")
    ap.add_argument("--model", help="override YuNet onnx path")
    ap.add_argument("--ss", type=float, help="start seconds")
    ap.add_argument("--t", type=float, help="duration seconds")
    ap.add_argument("--no-grade", action="store_true", help="skip global grade")
    ap.add_argument("--off", action="store_true", help="no retouch (pass-through for A/B)")
    ap.add_argument("--mask-debug", help="write mask preview video")
    ap.add_argument("--report", help="write JSON report")
    args = ap.parse_args()

    params = load_params(args.params)
    if args.model:
        params["model"] = args.model
    W, H, fps, has_audio = probe(args.input)
    cut = []
    if args.ss is not None:
        cut += ["-ss", f"{args.ss:.3f}"]
    cut_t = ["-t", f"{args.t:.3f}"] if args.t else []

    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", *cut, "-i", args.input, *cut_t,
         "-vf", "scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=bgr24",
         "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    # Convert to BT.709 limited-range YUV first, then grade in YUV (eq works on
    # YUV; grading before the conversion lets ffmpeg insert a BT.601 step).
    grade = "" if args.no_grade else "," + params["grade"]
    vf = f"scale=out_color_matrix=bt709:in_range=pc:out_range=tv,format=yuv420p{grade}"
    enc_cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{W}x{H}", "-r", f"{fps:.6f}", "-i", "-"]
    if has_audio:
        enc_cmd += [*cut, "-i", args.input, *cut_t, "-map", "0:v", "-map", "1:a",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    enc_cmd += ["-vf", vf, "-c:v", "libx264", *params["x264"],
                "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-movflags", "+faststart", "-shortest", args.output]
    enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE)
    dbg = None
    if args.mask_debug:
        dbg = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
             "-s", f"{W}x{H}", "-r", f"{fps:.6f}", "-i", "-", "-c:v", "libx264",
             "-crf", "23", "-pix_fmt", "yuv420p", args.mask_debug], stdin=subprocess.PIPE)

    tracker = FaceTracker(params, W, H, fps)
    frame_bytes = W * H * 3
    while True:
        buf = dec.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        face, weight = tracker.update(frame)
        mask = None
        if not args.off:
            frame, mask = retouch_frame(frame, face, weight, params)
        if dbg:
            view = (frame * 0.5).astype(np.uint8)
            if mask is not None:
                view[..., 1] = np.clip(view[..., 1] + mask * 200, 0, 255).astype(np.uint8)
            dbg.stdin.write(view.tobytes())
        enc.stdin.write(frame.tobytes())
    enc.stdin.close()
    dec.wait()
    rc = enc.wait()
    if dbg:
        dbg.stdin.close()
        dbg.wait()
    report = {"input": args.input, "output": args.output, "frames": tracker.frames,
              "face_frames": tracker.hits, "size": [W, H], "fps": round(fps, 3),
              "params": params}
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("frames", "face_frames", "size", "fps")}))
    sys.exit(rc)


if __name__ == "__main__":
    main()
