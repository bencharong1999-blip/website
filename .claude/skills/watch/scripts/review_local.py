#!/usr/bin/env python3
"""Local-file entry point for the Thai work kit; no cloud or ASR fallback."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--max-frames", type=int, default=12)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--timestamps")
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if not source.is_file():
        parser.error("source must be an accessible local file; send or download the file first")
    if not 1 <= args.max_frames <= 24:
        parser.error("--max-frames must be between 1 and 24")
    if not 64 <= args.resolution <= 1024:
        parser.error("--resolution must be between 64 and 1024")
    parent = args.out_dir.expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="review-", dir=parent))
    command = [sys.executable, str(Path(__file__).with_name("watch.py")), str(source),
               "--engine", "local", "--no-whisper", "--detail", "balanced",
               "--max-frames", str(args.max_frames), "--resolution", str(args.resolution),
               "--out-dir", str(work)]
    for flag, value in [("--start", args.start), ("--end", args.end), ("--timestamps", args.timestamps)]:
        if value is not None:
            command.extend([flag, value])
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    report = work / "review.md"
    report.write_text(result.stdout, encoding="utf-8")
    (work / "diagnostic.txt").write_text(result.stderr, encoding="utf-8")
    print(f"Report: {report}")
    print(result.stdout)
    if result.returncode:
        print(result.stderr, file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
