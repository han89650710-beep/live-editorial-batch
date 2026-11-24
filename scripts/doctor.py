#!/usr/bin/env python3
"""Preflight check: verify everything the pipeline needs is available."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check(label: str, ok: bool, hint: str = "") -> bool:
    print(f"[{'ok ' if ok else 'ERR'}] {label}" + (f"  -> {hint}" if not ok and hint else ""))
    return ok


def find_chrome() -> str | None:
    import os
    if os.environ.get("CHROME_PATH") and Path(os.environ["CHROME_PATH"]).exists():
        return os.environ["CHROME_PATH"]
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        str(Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe") if local else "",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def resolve_tool(config: dict, key: str) -> str | None:
    value = str(config.get(key, key))
    candidate = Path(value)
    if candidate.is_absolute():
        return str(candidate) if candidate.exists() else None
    return shutil.which(value)


def main() -> None:
    ok = True
    print(f"package root: {ROOT}")
    ok &= check("python >= 3.9", sys.version_info >= (3, 9), f"current: {sys.version.split()[0]}")

    config_path = ROOT / "config.json"
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as error:
            ok &= check("config.json", False, f"invalid JSON: {error}")
    else:
        ok &= check("config.json", False, "cp config.example.json config.json")

    for key, label in (("ffmpeg", "ffmpeg"), ("ffprobe", "ffprobe")):
        path = resolve_tool(config, key)
        ok &= check(f"{label} ({path or config.get(key, label)})", path is not None,
                    f"set config.{key} to an absolute path or add it to PATH")

    ok &= check("node", shutil.which("node") is not None, "install Node.js 18+")

    chrome = find_chrome()
    ok &= check("chrome", chrome is not None, "install Chrome or set CHROME_PATH")
    if chrome:
        print(f"      chrome: {chrome}")

    ok &= check("playwright-core", (ROOT / "node_modules" / "playwright-core").exists(),
                "run: npm install")
    try:
        from PIL import Image  # noqa: F401
        ok &= check("Pillow", True)
    except ImportError:
        ok &= check("Pillow", False, "run: pip install Pillow")

    try:
        import faster_whisper  # noqa: F401
        print("[ok ] faster-whisper (optional, for transcription)")
    except ImportError:
        print("[-- ] faster-whisper not installed (optional; use --srt instead)")

    try:
        import cv2  # noqa: F401
        model = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
        ok &= check("opencv + YuNet model (PIP face centering)", model.exists(),
                    "re-download the repo or assets/models/face_detection_yunet_2023mar.onnx")
    except ImportError:
        print("[-- ] opencv not installed (optional; the PIP falls back to a fixed crop)")

    if config:
        source = config.get("source", "")
        if source:
            path = Path(source) if Path(source).is_absolute() else ROOT / source
            ok &= check(f"source video {path}", path.exists(), "set config.source")
        font = (config.get("pip") or {}).get("label_font", "")
        if font:
            ok &= check(f"pip label font {font}", Path(font).exists(), "set pip.label_font or leave empty")
        free = shutil.disk_usage(ROOT).free / 1024 ** 3
        ok &= check(f"disk free {free:.1f} GB", free > 5, "need ~1-3 GB per video")
        print(f"      work_dir: {config.get('work_dir')}   output_dir: {config.get('output_dir')}")

    print("\nRESULT:", "ready" if ok else "fix the ERR lines above")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
