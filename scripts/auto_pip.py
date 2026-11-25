#!/usr/bin/env python3
"""Auto-center the PIP circle on the speaker's face.

Scans frames with OpenCV's YuNet face detector, takes the median face center
(robust against a single bad frame) and returns a square crop that keeps the
face in the middle of the circular PIP.

Usage:
  python scripts/auto_pip.py --video input.mp4 --out pip.json
  python scripts/auto_pip.py --video input.mp4 --time 20 --samples 1

Outputs JSON that you can paste into a story's "pip" field:

  {"crop": [x, y, w, h], "face": {...}, "confidence": "face" | "fallback"}

Then a story can override the global PIP:
  "pip": {"crop": [x, y, w, h], "x": 604, "y": 1010, "size": 340}

The YuNet model ships with the repo at assets/models/. If it is missing the
script still works and falls back to a centered guess.
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
from pathlib import Path

try:
    import cv2
except ImportError:  # keep the module importable so build_batch can degrade to a fixed crop
    cv2 = None

MODEL_NAME = "face_detection_yunet_2023mar.onnx"


def default_model() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "models" / MODEL_NAME


def readable_model(model: Path) -> Path:
    """OpenCV cannot open ONNX files under non-ASCII paths on Windows."""
    try:
        str(model).encode("ascii")
        return model
    except UnicodeEncodeError:
        pass
    cached = Path(tempfile.gettempdir()) / MODEL_NAME
    if not cached.exists() or cached.stat().st_size != model.stat().st_size:
        shutil.copyfile(model, cached)
    return cached


def make_detector(frame_w: int, frame_h: int, model: Path):
    """Return a YuNet detector sized for the frame, or None when unavailable."""
    if not model.exists():
        print(f"[auto-pip] model not found: {model}", file=sys.stderr)
        return None
    try:
        detector = cv2.FaceDetectorYN.create(
            str(readable_model(model)), "", (frame_w, frame_h), 0.6, 0.3, 5000
        )
    except Exception as error:  # pragma: no cover - depends on the cv2 build
        print(f"[auto-pip] cannot create face detector: {error}", file=sys.stderr)
        return None
    detector.setInputSize((frame_w, frame_h))
    return detector


def detect_faces(detector, frame):
    """Return the largest face as (x, y, w, h), or None."""
    if detector is None:
        return None
    _, faces = detector.detect(frame)
    if faces is None or len(faces) == 0:
        return None
    best = max(faces, key=lambda face: float(face[2]) * float(face[3]) * float(face[-1]))
    x, y, w, h = (int(round(float(value))) for value in best[:4])
    return (x, y, w, h)


def spread_times(total: float, count: int) -> list[float]:
    """Timestamps spread over the clip, skipping the first/last 5%."""
    if total <= 0:
        return [0.0]
    if count <= 1:
        return [round(total * 0.5, 3)]
    step = (total * 0.9) / max(1, count - 1)
    return [round(total * 0.05 + index * step, 3) for index in range(count)]


def read_frame(capture, time: float):
    capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, time) * 1000)
    ok, frame = capture.read()
    return frame if ok else None


def square_crop(face, frame_w: int, frame_h: int, max_side: int):
    if face is None:
        side = min(max_side or 720, frame_w, frame_h)
        cx, cy = frame_w // 2, int(frame_h * 0.28)
        confidence = "fallback"
    else:
        fx, fy, fw, fh = face
        # Face box centre sits around the nose; lift it slightly so the head has
        # as much air above as the chin has below inside the circle.
        cx, cy = fx + fw // 2, fy + fh // 2 - int(fh * 0.06)
        side = int(max(fh * 1.95, fw * 1.95, 520))
        # Shrink the crop when needed so the face can sit dead center:
        # the square must fit between the face center and the frame edge.
        centered_side = 2 * min(cx, frame_w - cx, cy, frame_h - cy)
        floor = int(max(fh * 2.0, fw * 2.0, 240))
        if centered_side >= floor:
            side = min(side, centered_side)
        side = min(side, max_side or side, frame_w, frame_h)
        confidence = "face"

    x = max(0, min(int(cx) - side // 2, frame_w - side))
    y = max(0, min(int(cy) - side // 2, frame_h - side))
    return [int(x), int(y), int(side), int(side)], confidence


def scan(video: Path, times: list[float], model: Path | None = None,
         max_side: int = 720) -> dict:
    """Detect the face at every timestamp and return the crop payload."""
    if cv2 is None:
        raise RuntimeError("OpenCV is required: pip install opencv-python-headless")
    video = Path(video)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video: {video}")

    first = read_frame(capture, 0.0)
    if first is None:
        capture.release()
        raise RuntimeError("cannot read a frame from the video")
    frame_h, frame_w = first.shape[:2]
    detector = make_detector(frame_w, frame_h, Path(model or default_model()))

    hits: list[float] = []
    boxes: list[tuple[int, int, int, int]] = []
    for time in times:
        frame = first if time <= 0 else read_frame(capture, time)
        if frame is None:
            continue
        face = detect_faces(detector, frame)
        if face is None:
            continue
        hits.append(time)
        boxes.append(face)
    capture.release()

    face = None
    if boxes:
        cx = int(statistics.median(box[0] + box[2] // 2 for box in boxes))
        cy = int(statistics.median(box[1] + box[3] // 2 for box in boxes))
        fw = int(statistics.median(box[2] for box in boxes))
        fh = int(statistics.median(box[3] for box in boxes))
        face = (cx - fw // 2, cy - fh // 2, fw, fh)

    crop, confidence = square_crop(face, frame_w, frame_h, max_side)
    return {
        "crop": crop,
        "confidence": confidence,
        "frame": [frame_w, frame_h],
        "time": round(statistics.median(hits), 2) if hits else 0.0,
        "scanned": len(hits),
        "face": None if face is None else {
            "x": int(face[0]), "y": int(face[1]), "w": int(face[2]), "h": int(face[3])
        },
        "note": "Paste crop into the story's pip.crop. If confidence is fallback, "
                "review the frame or pass --time to a moment where the face is clear.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Center the PIP crop on the speaker's face")
    parser.add_argument("--video", required=True)
    parser.add_argument("--time", type=float, default=0.0,
                        help="focus time in seconds (used when --samples 1)")
    parser.add_argument("--samples", type=int, default=9,
                        help="frames to scan across the clip, default 9")
    parser.add_argument("--size", type=int, default=720, help="max crop side, default 720")
    parser.add_argument("--model", default=str(default_model()), help="YuNet ONNX model path")
    parser.add_argument("--out", default="", help="write JSON to this file")
    args = parser.parse_args()

    probe = cv2.VideoCapture(str(args.video))
    if not probe.isOpened():
        sys.exit(f"cannot open video: {args.video}")
    fps = probe.get(cv2.CAP_PROP_FPS) or 0
    frames = probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    probe.release()
    total = float(frames) / float(fps) if fps and frames else 0.0

    if args.samples <= 1:
        times = [args.time]
    else:
        times = spread_times(total, args.samples)

    payload = scan(Path(args.video), times, Path(args.model), args.size)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[auto-pip] {payload['confidence']} "
              f"({payload['scanned']}/{len(times)} frames) -> {args.out}")
    print(text)


if __name__ == "__main__":
    main()
