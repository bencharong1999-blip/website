"""Small stdlib render cache. Import RenderCache; commands use {output}."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path, value):
    """Publish complete JSON, even if the process is interrupted during writing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".manifest-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class RenderCache:
    """Cache individual jobs. Use distinct output paths for concurrent jobs."""

    def __init__(self, cache_dir, *, dry_run=False, project_root=None):
        self.cache_dir = Path(cache_dir).resolve()
        self.dry_run = dry_run
        self.project_root = Path(project_root).resolve() if project_root is not None else None
        if self.project_root is not None and self.project_root == Path(self.project_root.anchor):
            raise ValueError("project_root must be a project directory, not the filesystem root")

    def _portable(self, value):
        """Normalize recipe paths only; execution always keeps the actual paths."""
        if self.project_root is None:
            return value
        if isinstance(value, str):
            prefix = str(self.project_root).rstrip(os.sep)
            return re.sub(re.escape(prefix) + r"(?=/|$)", "{project_root}", value)
        if isinstance(value, dict):
            return {self._portable(key): self._portable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._portable(item) for item in value]
        return value

    def _fingerprint(self, source):
        source = Path(source).resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"Expected a regular file: {source}")
        stat = source.stat()
        signature = [str(source), stat.st_dev, stat.st_ino, stat.st_size,
                     stat.st_mtime_ns, stat.st_ctime_ns]
        memo = self.cache_dir / "fingerprints" / (_digest(signature) + ".json")
        saved = _read_json(memo)
        if isinstance(saved, dict) and saved.get("signature") == signature:
            digest = saved.get("sha256")
            if isinstance(digest, str) and len(digest) == 64:
                return {"path": str(source), "size": stat.st_size, "sha256": digest}
        hasher = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        after = source.stat()
        if signature != [str(source), after.st_dev, after.st_ino, after.st_size,
                         after.st_mtime_ns, after.st_ctime_ns]:
            raise RuntimeError(f"Source changed while being fingerprinted: {source}")
        digest = hasher.hexdigest()
        if not self.dry_run:
            _write_json(memo, {"signature": signature, "sha256": digest})
        return {"path": str(source), "size": stat.st_size, "sha256": digest}

    def run_cached(self, name, inputs, settings, command, output):
        """Return a JSON-ready result with status cached/rendered/planned.

        inputs: every source, font, subtitle, timeline or script affecting this job.
        settings: JSON-compatible values, including relevant tool versions.
        command: argv list; at least one argument contains literal {output}.
        output: one file, atomically replaced only after command success/nonzero size.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a nonempty string")
        if not isinstance(command, (list, tuple)) or not command:
            raise ValueError("command must be a nonempty argv list")
        template = [os.fspath(part) for part in command]
        if not any("{output}" in part for part in template):
            raise ValueError("command must contain literal {output}")
        if not isinstance(settings, dict):
            raise ValueError("settings must be a JSON-compatible dict")
        output = Path(output).resolve()
        sources = [self._fingerprint(path) for path in inputs]
        if str(output) in {source["path"] for source in sources}:
            raise ValueError("output cannot replace an input")
        recipe = self._portable(
            {"schema": 1, "name": name, "inputs": sources, "settings": settings,
             "command": template, "output": str(output), "cwd": str(Path.cwd().resolve())}
        )
        key = _digest(recipe)
        job_id = _digest([name, self._portable(str(output))])
        manifest_path = self.cache_dir / "jobs" / (job_id + ".json")
        result = {"name": name, "status": "planned", "dry_run": self.dry_run,
                  "cache_key": key, "output": str(output), "manifest": str(manifest_path),
                  "command": template}
        previous = _read_json(manifest_path)
        if isinstance(previous, dict) and previous.get("cache_key") == key:
            if output.is_file() and output.stat().st_size > 0:
                current = self._fingerprint(output)
                recorded = previous.get("output_fingerprint")
                if isinstance(recorded, dict) and all(
                    current[field] == recorded.get(field) for field in ("size", "sha256")
                ):
                    result["status"] = "cached"
                    return result
        if self.dry_run:
            return result

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".render-", dir=output.parent) as work:
            temporary = Path(work) / output.name
            argv = [part.replace("{output}", str(temporary)) for part in template]
            # Deliberately use argv, never shell=True. Failed jobs leave old output intact.
            subprocess.run(argv, check=True)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError(f"Job produced no nonempty output: {name}")
            # Reject a result if a source changed during rendering.
            if [self._fingerprint(path) for path in inputs] != sources:
                raise RuntimeError(f"Input changed during render: {name}")
            os.replace(temporary, output)
        completed = {**recipe, "cache_key": key,
                     "completed_at": datetime.now(timezone.utc).isoformat(),
                     "output_fingerprint": self._portable(self._fingerprint(output))}
        _write_json(manifest_path, completed)
        result["status"] = "rendered"
        return result


def run_cached(name, inputs, settings, command, output, *, cache_dir, dry_run=False, project_root=None):
    """Convenience wrapper; a RenderCache instance can run multiple jobs."""
    return RenderCache(cache_dir, dry_run=dry_run, project_root=project_root).run_cached(
        name, inputs, settings, command, output
    )
