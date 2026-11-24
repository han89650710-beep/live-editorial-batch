#!/usr/bin/env python3
"""Turn a word-level transcript into a draft story.json.

This is the "拆解逐字稿、重新排列组合" step: it finds the sentences that match a
topic, ranks them, optionally reorders them, and writes a draft story you can edit.

Usage:
  python scripts/plan_from_transcript.py --transcript transcript.json \
      --topic "九块九,毛利,引流" --id v01 --name 01_topic --out stories/v01.json

  --order relevance   reorder by keyword score (default, "重新排列组合")
  --order timeline    keep the original speaking order
  --max-seconds N     optional budget; omit it and length follows the content
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def load_segments(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    segments = []
    for segment in data.get("segments", []):
        text = segment.get("text", "").strip()
        if not text:
            continue
        segments.append({
            "start": round(float(segment["start"]), 3),
            "end": round(float(segment["end"]), 3),
            "text": text,
            "words": segment.get("words", []),
        })
    return segments


def split_sentences(segments: list[dict]) -> list[dict]:
    """Split long ASR segments into sentence-sized pieces at punctuation."""
    sentences = []
    for segment in segments:
        text = segment["text"]
        parts = re.split(r"(?<=[。！？!?；;])", text)
        parts = [part.strip() for part in parts if part.strip()]
        if len(parts) <= 1:
            sentences.append(segment)
            continue
        total = sum(len(part) for part in parts)
        cursor = segment["start"]
        for part in parts:
            length = segment["end"] - segment["start"]
            piece = length * (len(part) / total) if total else 0
            sentences.append({
                "start": round(cursor, 3),
                "end": round(cursor + piece, 3),
                "text": part,
                "words": _slice_words(segment["words"], cursor, cursor + piece),
            })
            cursor += piece
    return sentences


def _slice_words(words: list[dict], start: float, end: float) -> list[dict]:
    return [word for word in words if start - 0.01 <= float(word.get("start", 0)) <= end + 0.01]


def score(sentence: dict, keywords: list[str]) -> int:
    return sum(sentence["text"].count(keyword) for keyword in keywords)


LIVE_LEN = 1.8   # seconds of full-screen live footage between pages
PAGE_MIN = 4.0   # a page shorter than this cannot hold its content
VERDICT_LEN = 4.0


def page_scene(kind: str, index: int, pages: int, start: float, end: float,
               captions: list[dict]) -> dict:
    """One placeholder page; the operator rewrites the copy but keeps the timing."""
    inside = [c for c in captions if start <= c["s"] < end]
    items = [{"label": c["text"][:18], "en": f"POINT {i + 1:02d}"}
             for i, c in enumerate(inside[:3])]
    if not items:
        items = [{"label": "待填要点", "en": "TODO"}]
    length = end - start
    return {
        "key": f"page{index + 1}",
        "type": kind,
        "bg": "dark",
        "start": round(start, 3),
        "end": round(end, 3),
        "kicker": f"待填 / PAGE {index + 1:02d}",
        "chapter": f"{index + 1:02d} / {pages:02d}",
        "ghost": f"{index + 1:02d}",
        "english": "TO BE WRITTEN",
        "headline": ["待填标题", "待填副标题"],
        "sub": "待填一句解释",
        "items": items,
        "beats": [round(min(0.6 + i * 1.4, max(0.4, length - 0.4)), 2) for i in range(len(items))],
        "kickerAt": 0.06,
        "headAt": 0.15,
        "englishAt": 0.3,
        "subAt": round(length * 0.5, 2),
    }


def build_scenes(total: float, captions: list[dict]) -> list[dict]:
    """Lay pages (and, when there is room, live cuts) across the whole timeline.

    Long enough stories get alternating live cuts so the 2.0 rules pass;
    short ones stay a plain 1.0 page sequence.
    """
    pairs = round((total - VERDICT_LEN) / (5.5 + LIVE_LEN))
    use_live = pairs >= 4 and (total - VERDICT_LEN - pairs * LIVE_LEN) / pairs >= PAGE_MIN

    scenes: list[dict] = []
    if use_live:
        page_len = (total - VERDICT_LEN - pairs * LIVE_LEN) / pairs
        cursor = 0.0
        for index in range(pairs):
            start, cursor = cursor, cursor + page_len
            scenes.append(page_scene("hook" if index == 0 else "list",
                                     index, pairs + 1, start, cursor, captions))
            live_start, cursor = cursor, cursor + LIVE_LEN
            scenes.append({"key": f"l{index + 1}", "type": "live", "bg": "live",
                           "start": round(live_start, 3), "end": round(cursor, 3)})
        scenes.append(page_scene("verdict", pairs, pairs + 1, cursor, total, captions))
        return scenes

    pages = max(3, round(total / 7))
    page_len = total / pages
    for index in range(pages):
        start = index * page_len
        end = total if index == pages - 1 else (index + 1) * page_len
        kind = "hook" if index == 0 else ("verdict" if index == pages - 1 else "list")
        scenes.append(page_scene(kind, index, pages, start, end, captions))
    return scenes


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a story.json from a transcript")
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--topic", required=True, help="comma separated keywords")
    parser.add_argument("--id", default="v01")
    parser.add_argument("--name", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--order", choices=["relevance", "timeline"], default="relevance")
    parser.add_argument("--max-seconds", type=float, default=0)
    parser.add_argument("--min-score", type=int, default=1)
    parser.add_argument("--source", default="", help="source video path for the story")
    args = parser.parse_args()

    keywords = [word.strip() for word in args.topic.split(",") if word.strip()]
    sentences = split_sentences(load_segments(Path(args.transcript)))

    picked = [item for item in sentences if score(item, keywords) >= args.min_score]
    if not picked:
        picked = sentences[: max(6, len(sentences) // 10)]

    if args.order == "relevance":
        picked.sort(key=lambda item: score(item, keywords), reverse=True)

    if args.max_seconds > 0:
        total, trimmed = 0.0, []
        for item in picked:
            length = item["end"] - item["start"]
            if total + length > args.max_seconds and trimmed:
                break
            trimmed.append(item)
            total += length
        picked = trimmed
        if args.order == "timeline":
            picked.sort(key=lambda item: item["start"])
    elif args.order == "timeline":
        picked.sort(key=lambda item: item["start"])

    segments, captions, cursor, offset = [], [], 0.0, 0.0
    for index, item in enumerate(picked):
        length = round(item["end"] - item["start"], 3)
        segments.append([item["start"], item["end"]])
        captions.append({
            "seg": index,
            "s": item["start"],
            "e": item["end"] - 0.02 if item["end"] - 0.02 > item["start"] else item["end"],
            "text": item["text"],
        })
        cursor += length

    total = round(cursor, 3)
    scenes = build_scenes(total, captions)
    has_live = any(scene["bg"] == "live" for scene in scenes)

    story = {
        "id": args.id,
        "name": args.name or f"{args.id}_draft",
        "version": "2.0" if has_live else "1.0",
        "embed_cover": False,
        "source": args.source,
        "segments": segments,
        "captions": captions,
        "scenes": scenes,
        "cover": {
            "issue": args.id.lstrip("v") or "01",
            "kicker": "待填 / TOPIC",
            "title": ["待填标题", "待填副标题"],
            "lines": ["待填要点一", "待填要点二", "待填要点三"],
            "time": segments[0][0] + 1 if segments else 0,
        },
        "qa_times": [round(total * ratio, 2) for ratio in (0.1, 0.35, 0.65, 0.9)],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[plan] {len(segments)} sentences / {total}s -> {out}")
    print("[plan] 下一步：填 source、改 headline、按口播调 beats，再跑 prepare")


if __name__ == "__main__":
    main()
