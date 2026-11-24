#!/usr/bin/env python3
"""Build a word-level transcript for caption sync.

Two modes:
  python transcribe.py input.mp4 -o transcript.json          # local Whisper
  python transcribe.py --srt captions.srt -o transcript.json # import existing subtitles

Output schema (consumed by your story config):
{
  "source": "...", "language": "zh", "duration": 123.4,
  "segments": [
    {"start": 1.0, "end": 3.2, "text": "...",
     "words": [{"w": "字", "start": 1.0, "end": 1.2}]}
  ]
}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def srt_seconds(value: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", value.strip())
    if not match:
        raise ValueError(f"bad srt timestamp: {value}")
    h, m, s, ms = match.groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def read_srt(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
    blocks = [block for block in raw.split("\n\n") if block.strip()]
    segments = []
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip()]
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        start_text, end_text = [part.strip() for part in lines[1].split("-->")]
        start, end = srt_seconds(start_text), srt_seconds(end_text)
        text = "".join(lines[2:]).strip()
        if not text:
            continue
        chars = [char for char in text if not char.isspace()]
        step = (end - start) / max(1, len(chars))
        words = [
            {"w": char, "start": round(start + index * step, 3),
             "end": round(start + (index + 1) * step, 3)}
            for index, char in enumerate(chars)
        ]
        segments.append({"start": round(start, 3), "end": round(end, 3), "text": text, "words": words})
    return segments


def inspect_duration(path: Path) -> float:
    try:
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        return round(float(result.stdout.strip()), 3)
    except Exception:
        return 0.0


def run_whisper(path: Path, model_name: str, language: str | None) -> tuple[list[dict], str, float]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit(
            "faster-whisper is not installed.\n"
            "Install it with:  pip install faster-whisper\n"
            "Or import existing subtitles:  python transcribe.py --srt captions.srt -o transcript.json"
        )

    model = WhisperModel(model_name, device="auto", compute_type="int8")
    segments, info = model.transcribe(
        str(path), language=language, word_timestamps=True,
        vad_filter=True, beam_size=5,
    )

    output = []
    for segment in segments:
        words = []
        for word in segment.words or []:
            text = word.word.strip()
            if not text:
                continue
            words.append({"w": text, "start": round(word.start, 3), "end": round(word.end, 3)})
        output.append({
            "start": round(segment.start, 3), "end": round(segment.end, 3),
            "text": segment.text.strip(), "words": words,
        })
    return output, info.language, round(info.duration, 3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Word-level transcript builder")
    parser.add_argument("input", nargs="?", help="video or audio file (whisper mode)")
    parser.add_argument("--srt", help="import an existing SRT instead of running whisper")
    parser.add_argument("-o", "--out", default="transcript.json")
    parser.add_argument("--model", default="small", help="whisper model: tiny/base/small/medium/large-v3")
    parser.add_argument("--language", default=None, help="e.g. zh; omit for auto detection")
    args = parser.parse_args()

    if args.srt:
        source = Path(args.srt)
        if not source.exists():
            sys.exit(f"subtitle file not found: {source}")
        segments = read_srt(source)
        payload = {
            "source": str(source), "language": "unknown",
            "duration": segments[-1]["end"] if segments else 0.0,
            "segments": segments, "mode": "srt-import",
        }
    else:
        if not args.input:
            sys.exit("provide a media file, or use --srt to import subtitles")
        media = Path(args.input)
        if not media.exists():
            sys.exit(f"media file not found: {media}")
        segments, language, duration = run_whisper(media, args.model, args.language)
        payload = {
            "source": str(media), "language": language,
            "duration": duration or inspect_duration(media),
            "segments": segments, "mode": "whisper", "model": args.model,
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    words = sum(len(segment["words"]) for segment in payload["segments"])
    print(f"[transcribe] {len(payload['segments'])} segments / {words} words -> {out}")


if __name__ == "__main__":
    main()
