#!/usr/bin/env python3
"""Local Whisper transcription + Thai word-boundary subtitle wrapping.

Audio stays on this machine. Model weights may download on the first run.
ASR word timestamps are estimates; no timestamps are fabricated by the wrapper.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import sys
import unicodedata
from pathlib import Path


def visible_length(text):
    return sum(unicodedata.category(c) not in {"Mn", "Mc", "Me"} for c in text)


def wrap_thai(text, width):
    from pythainlp.tokenize import word_tokenize
    # Never split a dictionary token or detach its combining marks to meet a width.
    tokens = word_tokenize(text, engine="newmm", keep_whitespace=True)
    if "".join(tokens) != text:
        raise ValueError("Tokenizer did not preserve the original text")
    lines, line = [], ""
    for token in tokens:
        if line.strip() and visible_length(line + token) > width:
            lines.append(line.rstrip())
            line = token.lstrip()
        else:
            line += token
    if line.strip():
        lines.append(line.rstrip())
    return "\n".join(lines)


def valid_words(raw):
    if isinstance(raw, dict):
        raw = raw.get("words")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Expected a non-empty words list")
    result, previous = [], -1.0
    for item in raw:
        word = item.get("word")
        if not isinstance(word, str):
            raise ValueError("Each word needs a string word field")
        start, end = float(item["start"]), float(item["end"])
        if not all(math.isfinite(v) for v in (start, end)) or start < 0 or end < start:
            raise ValueError("Invalid word timestamp")
        if start < previous - 0.001:
            raise ValueError("Word timestamps must be in source order")
        previous = start
        if word.strip():
            result.append({"word": word, "start": start, "end": end})
    if not result:
        raise ValueError("No spoken words found")
    return result


def cues_from_words(words, width, max_lines, max_seconds):
    cues, current = [], []

    def emit():
        if not current:
            return
        text = "".join(w["word"] for w in current).strip()
        start, end = current[0]["start"], max(w["end"] for w in current)
        if end <= start:
            raise ValueError("A subtitle cue has no measured duration")
        cues.append({"start": start, "end": end, "text": wrap_thai(text, width)})

    for word in words:
        proposed = current + [word]
        text = "".join(w["word"] for w in proposed).strip()
        too_long = word["end"] - proposed[0]["start"] > max_seconds
        too_many_lines = len(wrap_thai(text, width).splitlines()) > max_lines
        gap = bool(current and word["start"] - current[-1]["end"] > 0.6)
        if current and (too_long or too_many_lines or gap):
            emit()
            current = []
        current.append(word)
    emit()
    return cues


def srt_time(seconds):
    total = round(seconds * 1000)
    seconds, ms = divmod(total, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours:02}:{minute:02}:{sec:02},{ms:03}"


def ass_time(seconds):
    total = round(seconds * 100)
    seconds, cs = divmod(total, 100)
    minutes, sec = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    return f"{hour}:{minute:02}:{sec:02}.{cs:02}"


def ass_document(cues, args):
    if any(c in args.font for c in ",\r\n"):
        raise ValueError("Font name cannot contain a comma or newline")
    margin_x = round(args.frame_width * 0.08)
    margin_y = round(args.frame_height * 0.18)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {args.frame_width}
PlayResY: {args.frame_height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{args.font},{args.font_size},&H00FFFFFF,&H0000FFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,{margin_x},{margin_x},{margin_y},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    tags = {"plain": "", "fade": r"{\fad(90,90)}",
            "pop": r"{\fad(70,70)\fscx90\fscy90\t(0,100,\fscx100\fscy100)}"}[args.style]
    lines = []
    for cue in cues:
        text = cue["text"].replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")
        lines.append(f"Dialogue: 0,{ass_time(cue['start'])},{ass_time(cue['end'])},Default,,0,0,0,,{tags}{text}\n")
    return header + "".join(lines)


def versions():
    found = {}
    for name in ("faster-whisper", "pythainlp", "ctranslate2", "av"):
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found[name] = None
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--from-json", type=Path, help="Use measured word timestamps instead of running ASR")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--model", default="base", help="Multilingual model name or local CTranslate2 model directory")
    parser.add_argument("--language", default="th")
    parser.add_argument("--initial-prompt", default="ไทบ้านคุณภาพ")
    parser.add_argument("--model-cache", type=Path, help="Writable model cache; do not use the skill directory")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--max-cols", type=int, default=26)
    parser.add_argument("--max-lines", type=int, default=2)
    parser.add_argument("--max-seconds", type=float, default=4.0)
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--style", choices=("plain", "fade", "pop"), default="plain")
    parser.add_argument("--frame-width", type=int, default=1080)
    parser.add_argument("--frame-height", type=int, default=1920)
    parser.add_argument("--font", default="Noto Sans Thai")
    parser.add_argument("--font-size", type=int, default=52, help="Size in ASS design-resolution pixels")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        deps = versions()
        print(json.dumps({"ok": all(deps.values()), "dependencies": deps, "device": "cpu/int8", "models_bundled": False}))
        return 0 if all(deps.values()) else 2
    if bool(args.input) == bool(args.from_json) or args.out_dir is None:
        parser.error("Provide input OR --from-json, and --out-dir")
    if args.max_cols < 8 or not 1 <= args.max_lines <= 4 or not math.isfinite(args.max_seconds) or args.max_seconds <= 0 or args.cpu_threads < 1:
        parser.error("Invalid caption limits or thread count")
    if args.frame_width < 64 or args.frame_height < 64 or not 8 <= args.font_size <= 200:
        parser.error("Invalid ASS design resolution or font size")
    src = (args.from_json or args.input).resolve()
    if not src.is_file():
        raise ValueError(f"Input file does not exist: {src}")
    out = args.out_dir.resolve()
    names = ("captions.srt", "captions.ass", "words.json", "transcript.json", "report.json")
    if any((out / name).exists() for name in names):
        raise ValueError("Output exists; choose a fresh out-dir to preserve prior work")
    if not versions()["pythainlp"]:
        raise ValueError("PyThaiNLP is missing; run the bundled setup script in a writable directory")
    os.environ.setdefault("PYTHAINLP_DATA", str(out / "nlp-cache"))
    if args.from_json:
        raw = json.loads(src.read_text(encoding="utf-8"))
        words = valid_words(raw)
        language = raw.get("language", args.language) if isinstance(raw, dict) else args.language
        segments, origin = [], "provided_word_timestamps"
        model = None
    else:
        from faster_whisper import WhisperModel
        cache = args.model_cache.resolve() if args.model_cache else out / "model-cache"
        cache.mkdir(parents=True, exist_ok=True)
        model_instance = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=args.cpu_threads,
                                      download_root=str(cache), local_files_only=args.local_files_only)
        iterable, info = model_instance.transcribe(str(src), language=args.language, task="transcribe",
                                                  beam_size=5, word_timestamps=True, vad_filter=True,
                                                  condition_on_previous_text=False,
                                                  initial_prompt=args.initial_prompt or None)
        segments, raw_words = [], []
        for segment in iterable:
            segments.append({"start": segment.start, "end": segment.end, "text": segment.text})
            raw_words.extend({"word": w.word, "start": w.start, "end": w.end} for w in (segment.words or []))
        words = valid_words(raw_words)
        language, origin, model = info.language, "faster-whisper", args.model
    cues = cues_from_words(words, args.max_cols, args.max_lines, args.max_seconds)
    warnings = ["ASR word timestamps are estimates; review spelling and timing before posting.",
                "No face detection: set caption placement from actual frames."]
    overflow = [i + 1 for i, c in enumerate(cues) if len(c["text"].splitlines()) > args.max_lines
                or any(visible_length(line) > args.max_cols for line in c["text"].splitlines())]
    if overflow:
        warnings.append(f"Long unsplit tokens need visual review in cues: {overflow}")
    payload = {"source": str(src), "language": language, "origin": origin, "model": model, "words": words}
    report = {"ok": True, "origin": origin, "language": language, "model": model, "word_count": len(words),
              "cue_count": len(cues), "overflow_cues": overflow, "warnings": warnings,
              "dependencies": versions(), "outputs": {name: str(out / name) for name in names}}
    content = {
        "captions.srt": "".join(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n" for i, c in enumerate(cues, 1)),
        "captions.ass": ass_document(cues, args),
        "words.json": json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        "transcript.json": json.dumps({**{k: v for k, v in payload.items() if k != "words"}, "segments": segments, "cues": cues}, ensure_ascii=False, indent=2) + "\n",
        "report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, text in content.items():
        with (out / name).open("x", encoding="utf-8") as fh:
            fh.write(text)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
