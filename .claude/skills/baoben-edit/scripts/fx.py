#!/usr/bin/env python3
"""Add punch to a finished picture: shake, punch-zoom, flash, blackout and sound effects.

    fx.py PICTURE.mp4 VOICE.wav FX.json -o FINAL.mp4

FX.json (times are seconds on the edit timeline):

    {"shake":    [[10.36, 0.45, 22]],        # start, duration, amplitude in px
     "punch":    [[10.36, 0.60, 1.12]],      # start, duration, zoom factor
     "flash":    [0.40, 11.76],              # white flash start times
     "blackout": [[20.7, 0.9]],              # start, duration (fades in/out of black)
     "sfx":      [{"t": 0.40, "type": "impact", "gain": -4}, ...],
     "sfx_level": -9}                        # dB of the whole SFX bus under the voice

SFX types are generated here with ffmpeg (impact, boom, whoosh, heartbeat, riser), so
there is no third-party sound and nothing to license. The picture is re-encoded once
(1080x1920, same fps), voice + SFX are mixed and normalised to -16 LUFS / -1.5 dBTP.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

# Delivery loudness, the same targets as qc.py.
TARGET_I, TARGET_TP = -16, -1.5

# Margin (px) cropped off each edge so the frame can shake without showing borders.
SHAKE_MARGIN = 36

# Frames per second used to step flashes and blackouts.
STEP = 1 / 30

# ffmpeg lavfi recipes for each self-made sound effect (mono, 48 kHz).
SFX = {
    "impact": ("sine=f=48:d=0.9,volume=1.6,afade=t=out:st=0.05:d=0.85[a];"
               "anoisesrc=c=brown:d=0.25:a=0.6,lowpass=f=900,afade=t=out:st=0:d=0.25[b];"
               "[a][b]amix=inputs=2:normalize=0"),
    "boom": "sine=f=38:d=1.6,volume=2,afade=t=in:d=0.02,afade=t=out:st=0.1:d=1.5",
    "whoosh": ("anoisesrc=c=pink:d=0.7:a=0.5,bandpass=f=1400:width_type=h:w=2200,"
               "afade=t=in:d=0.45:curve=exp,afade=t=out:st=0.45:d=0.25"),
    "heartbeat": ("sine=f=52:d=0.16,afade=t=out:st=0.02:d=0.14,volume=2.2[l];"
                  "sine=f=46:d=0.2,afade=t=out:st=0.02:d=0.18,volume=1.6,adelay=260[d];"
                  "[l][d]amix=inputs=2:normalize=0"),
    "riser": ("anoisesrc=c=white:d=1.2:a=0.35,highpass=f=800,"
              "afade=t=in:d=1.1:curve=exp,afade=t=out:st=1.1:d=0.1"),
}


def run(cmd):
    """Run ffmpeg and raise with the error tail when it fails."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError("\n".join(p.stderr.splitlines()[-12:]))
    return p


def probe(path):
    """Return (width, height, fps, duration) of a video."""
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,r_frame_rate:format=duration", "-of", "json", path]).stdout
    d = json.loads(out)
    st = d["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return st["width"], st["height"], float(num) / float(den), float(d["format"]["duration"])


def between(spans):
    """Return an ffmpeg expression that is 1 inside any (start, dur) span, else 0."""
    if not spans:
        return "0"
    return "+".join(f"between(t,{s:.3f},{s + d:.3f})" for s, d in spans)


def video_filter(fx, w, h):
    """Build the picture filter: punch-zoom, shake, then flashes and blackouts."""
    punches = fx.get("punch", [])
    zoom = "1"
    for s, d, z in punches:
        # Jump in and ease back out over the span.
        zoom += f"+({z - 1:.3f})*between(t,{s:.3f},{s + d:.3f})*(1-(t-{s:.3f})/{d:.3f})"
    sw, sh = w + 2 * SHAKE_MARGIN, h + 2 * SHAKE_MARGIN
    graph = (f"scale=w='trunc({sw}*({zoom})/2)*2':h='trunc({sh}*({zoom})/2)*2':eval=frame,"
             f"pad=w='max(iw,{sw})':h='max(ih,{sh})':x=(ow-iw)/2:y=(oh-ih)/2")
    shake_x, shake_y = "0", "0"
    for s, d, a in fx.get("shake", []):
        decay = f"(1-(t-{s:.3f})/{d:.3f})"
        shake_x += f"+{a}*between(t,{s:.3f},{s + d:.3f})*{decay}*sin(t*97)"
        shake_y += f"+{a}*between(t,{s:.3f},{s + d:.3f})*{decay}*cos(t*83)"
    graph += (f",crop={w}:{h}:x='(iw-{w})/2+min({SHAKE_MARGIN},max(-{SHAKE_MARGIN},{shake_x}))'"
              f":y='(ih-{h})/2+min({SHAKE_MARGIN},max(-{SHAKE_MARGIN},{shake_y}))'")
    # Flashes: a few frames of white fading out.
    for t in fx.get("flash", []):
        for i, a in enumerate((0.85, 0.55, 0.3, 0.12)):
            graph += (f",drawbox=x=0:y=0:w=iw:h=ih:color=white@{a}:t=fill:"
                      f"enable='between(t,{t + i * STEP:.3f},{t + (i + 1) * STEP - 0.001:.3f})'")
    # Blackouts: ramp to black, hold, ramp back.
    for s, d in fx.get("blackout", []):
        ramp = min(0.25, d / 3)
        steps = 6
        for i in range(steps):
            a = (i + 1) / steps
            t0 = s + i * ramp / steps
            t1 = s + d - (i + 1) * ramp / steps
            graph += (f",drawbox=x=0:y=0:w=iw:h=ih:color=black@{a:.2f}:t=fill:"
                      f"enable='between(t,{t0:.3f},{t0 + ramp / steps - 0.001:.3f})+"
                      f"between(t,{t1:.3f},{t1 + ramp / steps - 0.001:.3f})'")
        graph += (f",drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:"
                  f"enable='between(t,{s + ramp:.3f},{s + d - ramp:.3f})'")
    return graph + ",setsar=1,format=yuv420p"


def make_sfx(fx, duration, tmp):
    """Render every SFX hit onto one bus WAV; return its path (or None if no SFX)."""
    hits = fx.get("sfx", [])
    if not hits:
        return None
    inputs, labels = [], []
    for i, h in enumerate(hits):
        recipe = SFX[h["type"]]
        path = os.path.join(tmp, f"sfx{i}.wav")
        run(["ffmpeg", "-v", "error", "-y", "-filter_complex",
             f"{recipe},aresample=48000,aformat=channel_layouts=mono,volume={h.get('gain', 0)}dB",
             "-t", "3", path])
        inputs += ["-i", path]
        labels.append(f"[{i}:a]adelay={int(h['t'] * 1000)}:all=1[s{i}]")
    graph = ";".join(labels) + ";" + "".join(f"[s{i}]" for i in range(len(hits)))
    graph += f"amix=inputs={len(hits)}:normalize=0,apad,atrim=0:{duration:.3f}[out]"
    bus = os.path.join(tmp, "sfx_bus.wav")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]", bus])
    return bus


def main():
    """Apply effects to the picture, mix voice + SFX and write the final MP4."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("picture")
    ap.add_argument("voice")
    ap.add_argument("fx")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    args = ap.parse_args()
    with open(args.fx, encoding="utf-8") as f:
        fx = json.load(f)
    w, h, fps, dur = probe(args.picture)
    with tempfile.TemporaryDirectory() as tmp:
        bus = make_sfx(fx, dur, tmp)
        level = fx.get("sfx_level", -9)
        cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", args.picture, "-i", args.voice]
        if bus:
            cmd += ["-i", bus]
            audio = (f"[1:a]aresample=48000,aformat=channel_layouts=mono[v];"
                     f"[2:a]volume={level}dB[s];[v][s]amix=inputs=2:normalize=0,"
                     f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11[a]")
        else:
            audio = f"[1:a]loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11[a]"
        graph = f"[0:v]{video_filter(fx, w, h)}[vout];{audio}"
        cmd += ["-filter_complex", graph, "-map", "[vout]", "-map", "[a]",
                "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf), "-r", f"{fps:g}",
                "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
                "-color_trc", "bt709", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-t", f"{dur:.3f}", "-movflags", "+faststart", args.output]
        run(cmd)
    print(json.dumps({"output": args.output, "duration": round(dur, 2)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
