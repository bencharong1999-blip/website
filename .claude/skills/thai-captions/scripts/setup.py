#!/usr/bin/env python3
"""Install optional ASR packages into a caller-selected writable venv."""
import argparse
import os
from pathlib import Path
import subprocess
import venv

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--venv", required=True, type=Path)
args = p.parse_args()
target = args.venv.resolve()
if target.exists():
    p.error("Choose a new virtual-environment directory; existing environments are preserved")
venv.EnvBuilder(with_pip=True).create(target)
python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
env = dict(os.environ, PIP_CACHE_DIR=str(target / "pip-cache"))
requirements = Path(__file__).resolve().parent / "requirements.txt"
subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)], check=True, env=env)
print(f"Ready: {python}")
