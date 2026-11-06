#!/usr/bin/env python3
"""Thai speech-to-text for Ben's recordings with Whisper via sherpa-onnx (no huggingface.co).

Models come from the k2-fsa/sherpa-onnx GitHub releases, which this cloud machine can
reach even when huggingface.co is blocked:

    python3 asr.py setup  --models DIR          # download whisper-small int8 + silero VAD
    python3 asr.py run    --models DIR AUDIO_OR_VIDEO -o out.json [--srt out.srt]

Output JSON: {"source": ..., "model": ..., "segments": [{"start", "end", "text"}]}
Times are seconds in the source file. The result is raw ASR: names, Isan words and
numbers can be wrong, so a person (or the script owner) must check it before it is
used as a quote or a caption.
"""
import argparse
import json
import os
import subprocess
import sys
import tarfile
import urllib.request

# Release assets used for setup (sherpa-onnx, Apache-2.0; Whisper weights MIT; Silero VAD MIT).
RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
WHISPER_TAR = "sherpa-onnx-whisper-small.tar.bz2"
WHISPER_DIR = "sherpa-onnx-whisper-small"
VAD_FILE = "silero_vad.onnx"

# Audio format Whisper and the VAD expect.
SAMPLE_RATE = 16000

# Whisper decodes at most 30 s at a time; keep merged speech chunks under this.
MAX_CHUNK = 28.0


def setup(models):
    """Download and unpack the Whisper small int8 model and Silero VAD into MODELS."""
    os.makedirs(models, exist_ok=True)
    wdir = os.path.join(models, WHISPER_DIR)
    if not os.path.exists(os.path.join(wdir, "small-encoder.int8.onnx")):
        tar = os.path.join(models, WHISPER_TAR)
        print(f"downloading {WHISPER_TAR} (~640 MB)", file=sys.stderr)
        urllib.request.urlretrieve(RELEASE + WHISPER_TAR, tar)
        with tarfile.open(tar) as t:
            t.extractall(models, filter="data")
        os.remove(tar)
        # Only the int8 files are used; drop the float ones to save ~1 GB of disk.
        for name in ("small-encoder.onnx", "small-decoder.onnx"):
            path = os.path.join(wdir, name)
            if os.path.exists(path):
                os.remove(path)
    vad = os.path.join(models, VAD_FILE)
    if not os.path.exists(vad):
        urllib.request.urlretrieve(RELEASE + VAD_FILE, vad)
    print(f"models ready in {models}", file=sys.stderr)


def load_audio(path):
    """Decode any audio/video file to 16 kHz mono float32 samples with ffmpeg."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1",
                          "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def speech_chunks(samples, vad_path):
    """Split audio into speech regions with Silero VAD, merged into chunks <= MAX_CHUNK s."""
    import sherpa_onnx
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = vad_path
    cfg.silero_vad.min_silence_duration = 0.35
    cfg.silero_vad.min_speech_duration = 0.25
    cfg.silero_vad.max_speech_duration = MAX_CHUNK
    cfg.sample_rate = SAMPLE_RATE
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
    window = cfg.silero_vad.window_size
    regions = []

    def drain():
        """Move finished speech segments out of the VAD queue."""
        while not vad.empty():
            seg = vad.front
            start = seg.start / SAMPLE_RATE
            regions.append((start, start + len(seg.samples) / SAMPLE_RATE))
            vad.pop()

    for i in range(0, len(samples), window):
        vad.accept_waveform(samples[i:i + window])
        drain()
    vad.flush()
    drain()
    # Merge neighbouring regions so Whisper gets sentence-sized context.
    merged = []
    for s, e in regions:
        if merged and e - merged[-1][0] <= MAX_CHUNK and s - merged[-1][1] < 0.8:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def transcribe(models, path, language="th"):
    """Run VAD + Whisper over a file and return a list of timed text segments."""
    import sherpa_onnx
    wdir = os.path.join(models, WHISPER_DIR)
    rec = sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=os.path.join(wdir, "small-encoder.int8.onnx"),
        decoder=os.path.join(wdir, "small-decoder.int8.onnx"),
        tokens=os.path.join(wdir, "small-tokens.txt"),
        language=language, task="transcribe", num_threads=os.cpu_count() or 2)
    samples = load_audio(path)
    out = []
    for start, end in speech_chunks(samples, os.path.join(models, VAD_FILE)):
        # Extra tail padding: Whisper tends to drop the last syllable (ครับ) at a hard cut.
        a = max(0, int((start - 0.2) * SAMPLE_RATE))
        b = min(len(samples), int((end + 0.6) * SAMPLE_RATE))
        stream = rec.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples[a:b])
        rec.decode_stream(stream)
        text = stream.result.text.strip()
        if text:
            out.append({"start": round(start, 2), "end": round(end, 2), "text": text})
            print(f"{start:7.2f}-{end:7.2f} {text}", file=sys.stderr, flush=True)
    return out


def srt_time(t):
    """Format seconds as an SRT timestamp."""
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    """Parse arguments and run setup or transcription."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["setup", "run"])
    ap.add_argument("source", nargs="?", help="audio or video file (run)")
    ap.add_argument("--models", required=True, help="folder for downloaded models")
    ap.add_argument("-o", "--output", help="JSON output path (run)")
    ap.add_argument("--srt", help="optional SRT output path (run)")
    ap.add_argument("--language", default="th")
    args = ap.parse_args()
    if args.command == "setup":
        setup(args.models)
        return 0
    if not args.source or not args.output:
        ap.error("run needs SOURCE and -o")
    segs = transcribe(args.models, args.source, args.language)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"source": os.path.basename(args.source), "model": "whisper-small int8 (sherpa-onnx)",
                   "note": "raw ASR — check before quoting", "segments": segs},
                  f, ensure_ascii=False, indent=2)
    if args.srt:
        with open(args.srt, "w", encoding="utf-8") as f:
            for i, s in enumerate(segs, 1):
                f.write(f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['text']}\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
