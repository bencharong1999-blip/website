#!/usr/bin/env python3
"""Render a Bao Ben episode from project.json + text/captions.json with a shot cache.

Reads the same project layout as the EP01 v02 package (schema 1):

    <project>/project.json          shots, sizes, encode settings, audio paths
    <project>/text/captions.json    on-screen text (start/end/text/highlight/motion)
    <project>/assets/...            sources, audio, fonts (never modified)

Writes only generated files:

    cache/clean/<id>-<key>.mp4      one clean shot, no audio
    cache/captioned/<id>-<key>.mp4  same shot with burned-in Thai captions
    cache/ass/<id>-<key>.ass        captions for that shot (shifted to shot time)
    text/captions.ass, text/captions.srt
    exports/picture_master.mp4, exports/captioned_master.mp4  (no audio)
    exports/<name>_final.mp4, exports/<name>_clean.mp4         (with mix audio)
    reports/render-jobs.json

A shot is re-encoded only when its source file, cut points or look settings change
(or, for the captioned layer, when the captions touching that shot change). Masters
are joined with stream copy, and audio is muxed without re-encoding the picture.

Usage:
    render.py PROJECT_DIR --dry-run          # check timeline + show what would render
    render.py PROJECT_DIR                     # render everything that is out of date
    render.py PROJECT_DIR --shots S01,S02     # render only these shots into exports/preview.mp4
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

# Bump when the ffmpeg recipe changes so old cache entries are not reused by mistake.
RECIPE_VERSION = "render-3"

# Defaults agreed with Ben (baoben-edit skill); project.json values override them.
DEFAULTS = {
    "width": 1080,
    "height": 1920,
    "fps": 60,
    "crf_clean": 18,
    "crf_captioned": 18,
    "preset": "medium",
    "threads": 0,
    "font": "Kanit",
    "font_size": 92,
    "accent_ass": "&H0000FFFF&",
    "caption_position": [540, 1400],
}

# Fonts bundled with the skill, used when the project has no assets/fonts folder.
SKILL_FONTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "fonts"))

# Timing slack (seconds) when checking that shots butt together without gaps.
TIMING_TOLERANCE = 0.011

# Still-image extensions: these sources are looped for the shot's duration.
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Colour metadata values that mean the source is BT.601 and must be converted to BT.709.
BT601_SPACES = {"smpte170m", "bt470bg", "bt601"}


def log(msg):
    """Print a progress line to stderr so stdout stays clean for --dry-run output."""
    print(msg, file=sys.stderr, flush=True)


def run(cmd):
    """Run an ffmpeg/ffprobe command and raise with its stderr tail if it fails."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"command failed: {' '.join(cmd[:6])} ...\n{tail}")
    return p.stdout


def sha256_text(text):
    """Return the hex SHA-256 of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_fingerprint(path, memo):
    """Return a cheap, stable fingerprint of a source file (size + mtime + head/tail hash)."""
    if path in memo:
        return memo[path]
    st = os.stat(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
        if st.st_size > (2 << 20):
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read(1 << 20))
    fp = f"{st.st_size}:{h.hexdigest()}"
    memo[path] = fp
    return fp


def load_project(root):
    """Load project.json and captions.json, filling in defaults for missing settings."""
    with open(os.path.join(root, "project.json"), encoding="utf-8") as f:
        project = json.load(f)
    settings = dict(DEFAULTS)
    settings.update({k: v for k, v in project.items() if k in DEFAULTS})
    cap_path = os.path.join(root, project.get("captions", "text/captions.json"))
    captions = []
    if os.path.exists(cap_path):
        with open(cap_path, encoding="utf-8") as f:
            captions = json.load(f)
    return project, settings, captions


def check_timeline(project, captions):
    """Return a list of problems: gaps/overlaps between shots, wrong total, captions out of range."""
    problems = []
    shots = sorted(project["shots"], key=lambda s: s["timeline_start"])
    if [s["id"] for s in shots] != [s["id"] for s in project["shots"]]:
        problems.append("shots are not listed in timeline order")
    t = 0.0
    for s in shots:
        if abs(s["timeline_start"] - t) > TIMING_TOLERANCE:
            problems.append(f"{s['id']}: starts at {s['timeline_start']} but previous shot ends at {t:.3f}")
        if s["duration"] <= 0:
            problems.append(f"{s['id']}: duration must be > 0")
        t = s["timeline_start"] + s["duration"]
    total = project.get("duration")
    if total is not None and abs(total - t) > TIMING_TOLERANCE:
        problems.append(f"shots end at {t:.3f}s but project duration is {total}s")
    for i, c in enumerate(captions):
        if c["end"] <= c["start"]:
            problems.append(f"caption {i + 1}: end <= start")
        if c["end"] > t + TIMING_TOLERANCE:
            problems.append(f"caption {i + 1}: ends at {c['end']}s after the picture ({t:.3f}s)")
    return problems


def ass_time(t):
    """Format seconds as an ASS timestamp H:MM:SS.cc."""
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def srt_time(t):
    """Format seconds as an SRT timestamp HH:MM:SS,mmm."""
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ass_escape(text):
    """Escape ASS override characters in caption text and turn newlines into \\N."""
    return (text.replace("\\n", "\n").replace("{", "(").replace("}", ")")
            .replace("\n", "\\N"))


def caption_body(c, settings, static=False):
    """Build the ASS dialogue text for one caption: motion tags + highlighted words.

    static=True drops the entry animation, used when a caption continues across a cut
    so it does not pop in a second time on the next shot.
    """
    text = ass_escape(c["text"])
    hl = ass_escape(c.get("highlight") or "")
    if hl and hl in text:
        accent = settings["accent_ass"]
        text = text.replace(hl, "{\\c" + accent + "}" + hl + "{\\c&H00FFFFFF&}", 1)
    x, y = settings["caption_position"]
    motion = c.get("motion", "pop")
    if static:
        tags = f"{{\\an5\\pos({x},{y})}}"
    elif motion == "soft":
        tags = f"{{\\an5\\pos({x},{y})\\fad(180,120)}}"
    else:
        tags = f"{{\\an5\\pos({x},{y})\\fscx82\\fscy82\\t(0,140,\\fscx100\\fscy100)\\fad(40,80)}}"
    return tags + text


def ass_document(settings, events):
    """Return a complete ASS file for the given (start, end, body) events."""
    w, h = settings["width"], settings["height"]
    style = (f"Style: Main,{settings['font']},{settings['font_size']},&H00FFFFFF,&H0000FFFF,"
             "&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,60,1")
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}",
             "WrapStyle: 2", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
             "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
             "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             style, "", "[Events]",
             "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for start, end, body in events:
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Main,,0,0,0,,{body}")
    return "\n".join(lines) + "\n"


def write_text_outputs(root, settings, captions):
    """Write text/captions.ass and text/captions.srt from captions.json (the only source)."""
    os.makedirs(os.path.join(root, "text"), exist_ok=True)
    events = [(c["start"], c["end"], caption_body(c, settings)) for c in captions]
    with open(os.path.join(root, "text", "captions.ass"), "w", encoding="utf-8") as f:
        f.write(ass_document(settings, events))
    with open(os.path.join(root, "text", "captions.srt"), "w", encoding="utf-8") as f:
        for i, c in enumerate(captions, 1):
            f.write(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n"
                    f"{c['text'].replace(chr(92) + 'n', chr(10))}\n\n")


def shot_ass(shot, settings, captions):
    """Return ASS text for captions overlapping a shot, shifted to the shot's own clock."""
    t0 = shot["timeline_start"]
    t1 = t0 + shot["duration"]
    events = []
    for c in captions:
        if c["end"] <= t0 or c["start"] >= t1:
            continue
        carried = c["start"] < t0
        events.append((max(0.0, c["start"] - t0), min(c["end"], t1) - t0,
                       caption_body(c, settings, static=carried)))
    if not events:
        return None
    return ass_document(settings, events)


def picture_filter(shot, settings):
    """Return the ffmpeg filtergraph that turns one source cut into a 1080x1920/60 shot."""
    w, h, fps = settings["width"], settings["height"], settings["fps"]
    color = shot.get("color", {})
    matrix = ""
    if color.get("color_space") in BT601_SPACES:
        matrix = ":in_color_matrix=bt601:out_color_matrix=bt709"
    graph = privacy_blur(shot.get("blur_boxes") or [])
    if shot.get("blur_fill"):
        graph += (f"[in]setsar=1,split=2[bgsrc][fgsrc];"
                 f"[bgsrc]scale={w // 4}:{h // 4}:force_original_aspect_ratio=increase{matrix},"
                 f"crop={w // 4}:{h // 4},gblur=sigma=12,scale={w}:{h},eq=brightness=-0.06[bg];"
                 f"[fgsrc]scale={w}:{h}:force_original_aspect_ratio=decrease{matrix}[fg];"
                 f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    else:
        graph += (f"[in]scale={w}:{h}:force_original_aspect_ratio=increase{matrix},"
                  f"crop={w}:{h},setsar=1")
    graph += f",fps={fps}"
    if shot.get("gentle_push"):
        frames = max(1, int(round(shot["duration"] * fps)))
        # Upscale 2x before zoompan so the slow push does not jitter on integer pixels.
        graph += (f",scale={w * 2}:{h * 2},zoompan=z='1+0.05*on/{frames}':d=1:"
                  f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}")
    # Clone the last frame a little so every shot has exactly duration*fps frames after
    # -frames:v trims it (fps/zoompan can come up a frame or two short at the tail).
    graph += ",tpad=stop_mode=clone:stop_duration=0.2,format=yuv420p[v]"
    return graph


def privacy_blur(boxes):
    """Return a filter prefix that blurs [x, y, w, h] boxes (fractions of the source frame).

    Used to hide patient wristbands, name tags or screens before any scaling, so the
    blur follows the picture through crops and pushes. Output label is [in].
    """
    if not boxes:
        return "[0:v]null[in];"
    graph, last = "", "0:v"
    for i, (x, y, bw, bh) in enumerate(boxes):
        graph += (f"[{last}]split=2[m{i}][c{i}];"
                  f"[c{i}]crop=iw*{bw}:ih*{bh}:iw*{x}:ih*{y},boxblur=luma_radius=24:luma_power=3[b{i}];"
                  f"[m{i}][b{i}]overlay=W*{x}:H*{y}[o{i}];")
        last = f"o{i}"
    return graph + f"[{last}]null[in];"


def encode_args(settings, crf):
    """Return identical H.264 settings for every shot so masters can be stream-copied."""
    args = ["-c:v", "libx264", "-preset", str(settings["preset"]), "-crf", str(crf),
            "-r", str(settings["fps"]), "-pix_fmt", "yuv420p", "-g", str(settings["fps"]),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-an", "-movflags", "+faststart"]
    if settings["threads"]:
        args += ["-threads", str(settings["threads"])]
    return args


def fonts_dir(root):
    """Return the font folder to give libass: project assets/fonts if present, else the skill's."""
    proj = os.path.join(root, "assets", "fonts")
    return proj if os.path.isdir(proj) else SKILL_FONTS


def plan_shots(root, project, settings, captions, memo):
    """Work out cache paths and keys for every shot's clean and captioned layer."""
    plan = []
    look = {k: settings[k] for k in ("width", "height", "fps", "crf_clean", "preset")}
    cap_look = {k: settings[k] for k in ("font", "font_size", "accent_ass",
                                         "caption_position", "crf_captioned", "preset")}
    for shot in project["shots"]:
        src = os.path.join(root, shot["source"])
        if not os.path.exists(src):
            raise FileNotFoundError(f"{shot['id']}: source not found: {shot['source']}")
        spec = {k: shot.get(k) for k in ("source_start", "duration", "blur_fill", "blur_boxes",
                                         "gentle_push", "color")}
        clean_key = sha256_text(json.dumps([RECIPE_VERSION, file_fingerprint(src, memo),
                                            spec, look], sort_keys=True))[:16]
        ass = shot_ass(shot, settings, captions)
        cap_key = None
        if ass is not None:
            cap_key = sha256_text(json.dumps([clean_key, ass, cap_look, fonts_dir(root)],
                                             sort_keys=True))[:16]
        sid = shot["id"]
        plan.append({
            "shot": shot,
            "src": src,
            "clean": os.path.join(root, "cache", "clean", f"{sid}-{clean_key}.mp4"),
            "ass_text": ass,
            "ass": os.path.join(root, "cache", "ass", f"{sid}-{cap_key}.ass") if cap_key else None,
            "captioned": (os.path.join(root, "cache", "captioned", f"{sid}-{cap_key}.mp4")
                          if cap_key else None),
        })
    return plan


def render_clean(item, settings):
    """Encode one clean shot from its source into the cache (atomic write)."""
    shot = item["shot"]
    tmp = item["clean"] + ".part.mp4"
    os.makedirs(os.path.dirname(item["clean"]), exist_ok=True)
    if os.path.splitext(item["src"])[1].lower() in IMAGE_EXTS:
        # A still photo: loop it at the target frame rate for the shot's duration.
        source_args = ["-loop", "1", "-framerate", str(settings["fps"]),
                       "-t", str(shot["duration"]), "-i", item["src"]]
    else:
        source_args = ["-ss", str(shot.get("source_start", 0)),
                       "-t", str(shot["duration"]), "-i", item["src"]]
    run(["ffmpeg", "-hide_banner", "-y", *source_args,
         "-filter_complex", picture_filter(shot, settings), "-map", "[v]",
         "-frames:v", str(int(round(shot["duration"] * settings["fps"]))),
         *encode_args(settings, settings["crf_clean"]), tmp])
    os.replace(tmp, item["clean"])


def render_captioned(item, settings, root):
    """Burn the shot's captions onto its cached clean shot (atomic write)."""
    os.makedirs(os.path.dirname(item["ass"]), exist_ok=True)
    os.makedirs(os.path.dirname(item["captioned"]), exist_ok=True)
    with open(item["ass"], "w", encoding="utf-8") as f:
        f.write(item["ass_text"])
    tmp = item["captioned"] + ".part.mp4"
    vf = f"ass={filter_path(item['ass'])}:fontsdir={filter_path(fonts_dir(root))}"
    run(["ffmpeg", "-hide_banner", "-y", "-i", item["clean"], "-vf", vf,
         *encode_args(settings, settings["crf_captioned"]), tmp])
    os.replace(tmp, item["captioned"])


def filter_path(path):
    """Escape a path for use inside an ffmpeg filter argument."""
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


def concat(paths, out):
    """Join shots with the concat demuxer using stream copy (no re-encode)."""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    lst = out + ".txt"
    with open(lst, "w", encoding="utf-8") as f:
        for p in paths:
            f.write("file '" + os.path.abspath(p).replace("'", "'\\''") + "'\n")
    run(["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", "-movflags", "+faststart", out])
    os.remove(lst)


def mux(video, audio, out):
    """Put the mix audio under a master: video stream-copied, audio AAC 48 kHz."""
    run(["ffmpeg", "-hide_banner", "-y", "-i", video, "-i", audio, "-map", "0:v:0",
         "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-shortest", "-movflags", "+faststart", out])


def main():
    """Parse arguments, check the timeline, render out-of-date shots and assemble exports."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", help="project folder containing project.json")
    ap.add_argument("--dry-run", action="store_true", help="check and list work without rendering")
    ap.add_argument("--shots", help="comma-separated shot ids to render as exports/preview.mp4")
    ap.add_argument("--no-captions", action="store_true", help="skip the captioned layer")
    args = ap.parse_args()

    root = os.path.abspath(args.project)
    project, settings, captions = load_project(root)
    problems = check_timeline(project, captions)
    for p in problems:
        log(f"WARN {p}")

    memo = {}
    plan = plan_shots(root, project, settings, captions, memo)
    if args.shots:
        wanted = [s.strip() for s in args.shots.split(",") if s.strip()]
        unknown = set(wanted) - {i["shot"]["id"] for i in plan}
        if unknown:
            sys.exit(f"unknown shot ids: {', '.join(sorted(unknown))}")
        plan = [i for i in plan if i["shot"]["id"] in wanted]

    use_caps = not args.no_captions
    summary = []
    for item in plan:
        clean_ok = os.path.exists(item["clean"])
        cap_ok = (item["captioned"] is None or not use_caps or os.path.exists(item["captioned"]))
        summary.append({"id": item["shot"]["id"],
                        "clean": "cached" if clean_ok else "render",
                        "captioned": ("none" if item["captioned"] is None or not use_caps
                                      else "cached" if cap_ok else "render")})
    if args.dry_run:
        print(json.dumps({"problems": problems, "shots": summary}, ensure_ascii=False, indent=2))
        return 1 if problems else 0
    if problems and not args.shots:
        sys.exit("timeline problems found — fix project.json/captions.json or use --shots for a preview")

    write_text_outputs(root, settings, captions)
    started = time.time()
    jobs = []
    for item, row in zip(plan, summary):
        t = time.time()
        if row["clean"] == "render":
            log(f"{row['id']}: rendering clean shot")
            render_clean(item, settings)
        if row["captioned"] == "render":
            log(f"{row['id']}: burning captions")
            render_captioned(item, settings, root)
        jobs.append({**row, "seconds": round(time.time() - t, 2)})

    exports = os.path.join(root, "exports")
    cleans = [i["clean"] for i in plan]
    capped = [i["captioned"] if (use_caps and i["captioned"]) else i["clean"] for i in plan]
    outputs = []
    if args.shots:
        out = os.path.join(exports, "preview.mp4")
        concat(capped, out)
        outputs.append(out)
    else:
        picture = os.path.join(exports, "picture_master.mp4")
        captioned = os.path.join(exports, "captioned_master.mp4")
        concat(cleans, picture)
        concat(capped, captioned)
        outputs += [picture, captioned]
        mix = (project.get("audio") or {}).get("mix")
        if mix and os.path.exists(os.path.join(root, mix)):
            base = f"{project.get('code', 'EP')}_{project.get('version', 'v01')}"
            final = os.path.join(exports, f"{base}_final.mp4")
            clean = os.path.join(exports, f"{base}_clean.mp4")
            mux(captioned, os.path.join(root, mix), final)
            mux(picture, os.path.join(root, mix), clean)
            outputs += [final, clean]
        else:
            log("no audio.mix found — exported picture-only masters")

    os.makedirs(os.path.join(root, "reports"), exist_ok=True)
    report = {"recipe": RECIPE_VERSION, "ffmpeg": shutil.which("ffmpeg"),
              "seconds": round(time.time() - started, 2), "shots": jobs,
              "outputs": [os.path.relpath(o, root) for o in outputs]}
    with open(os.path.join(root, "reports", "render-jobs.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
