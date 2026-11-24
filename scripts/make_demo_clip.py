#!/usr/bin/env python3
"""Generate a synthetic 36s vertical demo clip so the pipeline can run end to end
without any copyrighted footage."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "demo" / "demo_source.mp4"


def resolve_ffmpeg() -> str:
    env = os.environ.get("FFMPEG")
    if env and Path(env).exists():
        return env
    config_path = ROOT / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        value = str(config.get("ffmpeg", "ffmpeg"))
        candidate = Path(value)
        if candidate.is_absolute() and candidate.exists():
            return str(candidate)
        found = shutil.which(value)
        if found:
            return found
    found = shutil.which("ffmpeg")
    if found:
        return found
    sys.exit("ffmpeg not found. Set FFMPEG env var or config.ffmpeg")


def main() -> None:
    ffmpeg = resolve_ffmpeg()

    base = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=36",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=36",
    ]
    with_text = [
        "-vf",
        "drawtext=text='DEMO %{pts\\:hms}':fontsize=72:fontcolor=white:"
        "box=1:boxcolor=black@0.55:boxborderw=18:x=(w-text_w)/2:y=160",
    ]
    common = [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(TARGET),
    ]

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(base + with_text + common, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        print("[demo] drawtext unavailable, falling back to plain test pattern")
        result = subprocess.run(base + common, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        sys.exit(result.stdout.decode("utf-8", "replace")[-1500:])
    print(f"[demo] created {TARGET}")


if __name__ == "__main__":
    main()
