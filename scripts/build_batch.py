#!/usr/bin/env python3
"""Vertical short-video batch editor.

Config-driven, deterministic pipeline:
  prepare -> media -> covers -> capture -> render (includes QA)

Every rule is enforced with an assertion, so a bad story cannot silently
produce a video.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.json"

BEAT = 1.5            # visual rhythm: something visible must change every 1.5s
MAX_CONTENT_GAP = 4.5  # longest allowed gap between content nodes on a page
MAX_HEAD_DELAY = 1.6   # a page must show its headline within 1.6s
EMBED_FRAMES = 15      # 0.5s cover intro at 30fps


def die(message: str) -> None:
    print(f"[error] {message}", file=sys.stderr)
    raise SystemExit(2)


def resolve(path_like: str, base: Path) -> Path:
    path = Path(path_like)
    return path if path.is_absolute() else (base / path)


def tool(value: str) -> str:
    """Resolve an executable from config: absolute path or PATH lookup."""
    candidate = Path(value)
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)
    found = shutil.which(value)
    if not found:
        die(f"cannot find executable: {value}. Install it or fix config.json")
    return found


def run(command: list[str], cwd: Path, log_path: Path | None = None) -> str:
    result = subprocess.run(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0:
        tail = result.stdout[-4000:]
        raise RuntimeError(f"command failed ({result.returncode}); see {log_path or 'output'}\n{tail}")
    return result.stdout


def probe(ffprobe: str, path: Path) -> dict:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", check=True,
    )
    return json.loads(result.stdout)


def srt_time(value: float) -> str:
    ms = int(round(value * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ass_time(value: float) -> str:
    cs = int(round(value * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def merge_ranges(ranges: list[tuple[float, float]]) -> list[list[float]]:
    merged: list[list[float]] = []
    for start, end in ranges:
        if merged and abs(start - merged[-1][1]) < 0.02:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged


# --------------------------------------------------------------------------- #
# story loading and rule checks
# --------------------------------------------------------------------------- #

def load_stories(config: dict) -> list[dict]:
    stories_dir = resolve(config.get("stories_dir", "stories"), ROOT)
    default_source = config.get("source", "")
    fps = int(config.get("fps", 30))

    stories = []
    paths = sorted(stories_dir.glob("*.json"))
    for path in paths:
        story = json.loads(path.read_text(encoding="utf-8-sig"))
        if "id" not in story:
            die(f"{path.name}: missing id")
        source = story.get("source") or default_source
        if not source:
            die(f"{story['id']}: no source video. Set config.source or story.source")
        source_path = resolve(source, ROOT)
        if not source_path.exists():
            die(f"{story['id']}: source video not found: {source_path}")
        story["source_path"] = str(source_path)

        segments = []
        offset = 0.0
        for start, end in story["segments"]:
            frames = round((end - start) * fps)
            duration = frames / fps
            segments.append({
                "source_start": start, "source_end": end,
                "frames": frames, "duration": duration, "offset": offset,
            })
            offset += duration
        story["segments_calc"] = segments
        story["frame_count"] = sum(segment["frames"] for segment in segments)
        story["duration"] = story["frame_count"] / fps

        story["captions_calc"] = []
        for caption in story["captions"]:
            index = caption["seg"]
            if index >= len(segments):
                die(f"{story['id']}: caption references missing segment {index}")
            segment = segments[index]
            if caption["s"] < segment["source_start"] - 0.01 or caption["e"] > segment["source_end"] + 0.01:
                die(f"{story['id']}: caption outside segment: {caption}")
            local_start = segment["offset"] + (caption["s"] - segment["source_start"])
            local_end = segment["offset"] + (caption["e"] - segment["source_start"])
            if local_end > story["duration"] + 0.001:
                die(f"{story['id']}: caption beyond total duration (leave 0.02s margin)")
            story["captions_calc"].append({
                "start": round(local_start, 3), "end": round(local_end, 3), "text": caption["text"],
            })

        scenes = story["scenes"]
        if abs(scenes[0]["start"]) > 0.001 or abs(scenes[-1]["end"] - story["duration"]) > 0.001:
            die(f"{story['id']}: scenes must cover the whole timeline")
        for left, right in zip(scenes, scenes[1:]):
            if abs(left["end"] - right["start"]) > 0.001:
                die(f"{story['id']}: scene gap at {left['end']}")

        story["pip_ranges"] = merge_ranges([
            (scene["start"], scene["end"]) for scene in scenes if scene.get("bg") != "live"
        ])

        if str(story.get("version", "")).startswith("2.0"):
            live = [scene for scene in scenes if scene.get("bg") == "live"]
            if len(live) < 4:
                die(f"{story['id']}: 2.0 needs >= 4 live scenes, got {len(live)}")
            for left, right in zip(scenes, scenes[1:]):
                if left.get("bg") == "dark" and right.get("bg") == "dark":
                    die(f"{story['id']}: adjacent dark scenes at {left['end']}s")
            ratio = sum(scene["end"] - scene["start"] for scene in live) / story["duration"]
            if not 0.18 <= ratio <= 0.32:
                die(f"{story['id']}: live ratio {ratio:.1%} outside 18-32%")

        stories.append(story)

    if not stories:
        die(f"no stories found in {stories_dir}")
    return stories


def rhythm_report(story: dict) -> dict:
    def scene_times(scene: dict) -> list[float]:
        if scene.get("bg") == "live":
            return []
        values = [
            scene.get("kickerAt", 0.06), scene.get("headAt", 0.14), scene.get("subAt", 0.38),
            scene.get("englishAt", 0.28), scene.get("tagAt", 0.58), scene.get("noteAt", 0.76),
            scene.get("bigAt", 0.42), scene.get("labelAt", 0.66), scene.get("quoteAt", 0.46),
        ]
        values += [float(beat) for beat in scene.get("beats", [])]
        if scene.get("type") == "versus":
            values += [float(scene.get("leftAt", 0.36)), float(scene.get("rightAt", 0.54)),
                       float(scene.get("midAt", 0.92))]
            for side in ("left", "right"):
                values += [float(beat) for beat in (scene.get(side) or {}).get("beats", [])]
        return [scene["start"] + value for value in values if scene["start"] + value <= scene["end"]]

    content = [0.0]
    for scene in story["scenes"]:
        content += scene_times(scene)
        content.append(scene["end"])
    content = sorted({round(value, 3) for value in content})

    ticks = []
    for scene in story["scenes"]:
        value = scene["start"] + BEAT
        while value <= scene["end"] + 0.001:
            ticks.append(round(value, 3))
            value += BEAT

    full = sorted(set(content) | set(ticks))

    def gaps(points: list[float]) -> dict:
        diffs = [round(b - a, 3) for a, b in zip(points, points[1:])]
        return {"max": max(diffs) if diffs else 0.0,
                "avg": round(sum(diffs) / len(diffs), 3) if diffs else 0.0}

    return {"content": gaps(content), "withTicks": gaps(full), "points": len(full)}


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #

def story_dir(config: dict, story: dict) -> Path:
    return resolve(config.get("work_dir", "work"), ROOT) / story["id"]


def prepare(config: dict, story: dict) -> Path:
    directory = story_dir(config, story)
    (directory / "frames").mkdir(parents=True, exist_ok=True)
    (directory / "qa").mkdir(parents=True, exist_ok=True)

    template = (ROOT / "assets" / "web_motion_batch.html").read_text(encoding="utf-8")
    html = template.replace("__STORY_JSON__", json.dumps(story, ensure_ascii=False))
    html_path = directory / f"{story['id']}.html"
    html_path.write_text(html, encoding="utf-8")

    write_captions(config, story)

    rhythm = rhythm_report(story)
    if story.get("rhythm"):
        if rhythm["content"]["max"] > MAX_CONTENT_GAP:
            die(f"{story['id']}: content gap {rhythm['content']['max']}s > {MAX_CONTENT_GAP}s")
        if rhythm["withTicks"]["max"] > BEAT + 0.0001:
            die(f"{story['id']}: visual gap {rhythm['withTicks']['max']}s > {BEAT}s")
        for scene in story["scenes"]:
            if scene.get("bg") == "live":
                continue
            head = float(scene.get("headAt", 0.14))
            if head > MAX_HEAD_DELAY:
                die(f"{story['id']}: scene {scene['key']} headline at {head}s > {MAX_HEAD_DELAY}s")
        print(f"rhythm {story['id']}: {json.dumps(rhythm, ensure_ascii=False)}")

    design = {
        "id": story["id"], "name": story["name"], "source": story["source_path"],
        "segments": story["segments"], "segments_calc": story["segments_calc"],
        "frame_count": story["frame_count"], "duration": story["duration"],
        "fps": config.get("fps", 30), "canvas": [config.get("width", 1080), config.get("height", 1920)],
        "scenes": story["scenes"], "captions": story["captions_calc"],
        "pip_ranges": story["pip_ranges"], "rhythm": rhythm,
    }
    (directory / "design.json").write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
    return html_path


def write_captions(config: dict, story: dict) -> None:
    directory = story_dir(config, story)
    subtitle = config.get("subtitle", {})
    font_name = subtitle.get("font", "Microsoft YaHei")
    size = subtitle.get("size", 56)
    margin_v = subtitle.get("margin_v", 248)

    srt_blocks, ass_events = [], []
    for index, caption in enumerate(story["captions_calc"], 1):
        srt_blocks.append(
            f"{index}\n{srt_time(caption['start'])} --> {srt_time(caption['end'])}\n{caption['text']}\n"
        )
        text = caption["text"].replace("\n", r"\N")
        ass_events.append(
            f"Dialogue: 0,{ass_time(caption['start'])},{ass_time(caption['end'])},Default,,0,0,0,,{text}"
        )
    (directory / "captions.srt").write_text("\n".join(srt_blocks), encoding="utf-8-sig")

    ass = f"""[Script Info]
Title: BATCH_CAPTIONS
ScriptType: v4.00+
PlayResX: {config.get("width", 1080)}
PlayResY: {config.get("height", 1920)}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{size},&H00FFFFFF,&H00FFFFFF,&H60000000,&H60000000,-1,0,0,0,100,100,0,0,3,12,0,2,70,70,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ass_events) + "\n"
    (directory / "captions.ass").write_text(ass, encoding="utf-8-sig")


def build_ring(config: dict) -> Path:
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))
    pip = config.get("pip", {})
    size = int(pip.get("size", 340))
    x, y = int(pip.get("x", 604)), int(pip.get("y", 1010))
    label = pip.get("label", "")

    target = resolve(config.get("work_dir", "work"), ROOT) / "pip_ring.png"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - 16, y - 16, x + size + 16, y + size + 16),
                 outline=(250, 247, 240, 255), width=8)
    font_file = pip.get("label_font", "")
    font = None
    if label and font_file and Path(font_file).exists():
        try:
            font = ImageFont.truetype(font_file, 24)
        except OSError:
            font = None
    if label and font is not None:
        box_w = 124 if font.getlength(label) < 90 else 150
        draw.rounded_rectangle((x, y + size + 26, x + box_w, y + size + 68), radius=20, fill=(197, 52, 42, 255))
        draw.text((x + 22, y + size + 33), label, font=font, fill=(255, 255, 255, 255))
    image.save(target)
    return target


def build_media(config: dict, story: dict) -> None:
    directory = story_dir(config, story)
    ffmpeg = tool(config.get("ffmpeg", "ffmpeg"))
    fps = int(config.get("fps", 30))
    source = story["source_path"]

    segment_files = []
    for index, segment in enumerate(story["segments_calc"]):
        target = directory / f"seg_{index}.mp4"
        if not target.exists():
            run([
                ffmpeg, "-hide_banner", "-y", "-ss", f"{segment['source_start']:.3f}", "-i", source,
                "-t", f"{segment['duration']:.6f}", "-an", "-vf", f"setpts=PTS-STARTPTS,fps={fps}",
                "-frames:v", str(segment["frames"]), "-c:v", "libx264", "-preset", "veryfast", "-crf", "6",
                "-pix_fmt", "yuv420p", "-video_track_timescale", "15360", str(target),
            ], directory, directory / f"seg_{index}.log")
        segment_files.append(target)

    if len(segment_files) == 1:
        shutil.copy2(segment_files[0], directory / "base.mp4")
    else:
        concat_file = directory / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{path.name}'" for path in segment_files) + "\n", encoding="utf-8")
        run([ffmpeg, "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
             "-c", "copy", str(directory / "base.mp4")], directory, directory / "concat.log")

    wavs = []
    for index, segment in enumerate(story["segments_calc"]):
        target = directory / f"audio_{index}.wav"
        if not target.exists():
            run([
                ffmpeg, "-hide_banner", "-y", "-ss", f"{segment['source_start']:.3f}", "-i", source,
                "-t", f"{segment['duration']:.6f}", "-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
                str(target),
            ], directory, directory / f"audio_{index}.log")
        wavs.append(target)

    if len(wavs) == 1:
        shutil.copy2(wavs[0], directory / "audio.wav")
    else:
        inputs: list[str] = []
        for wav in wavs:
            inputs += ["-i", str(wav)]
        labels = "".join(f"[{index}:a]" for index in range(len(wavs)))
        run([ffmpeg, "-hide_banner", "-y", *inputs, "-filter_complex",
             f"{labels}concat=n={len(wavs)}:v=0:a=1[a]", "-map", "[a]", "-c:a", "pcm_s16le",
             str(directory / "audio.wav")], directory, directory / "audio_concat.log")

    run([ffmpeg, "-hide_banner", "-y", "-i", "audio.wav", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-ac", "2", "-t", f"{story['duration']:.6f}", "audio.m4a"],
        directory, directory / "audio_encode.log")


def write_capture_jobs(config: dict, stories: list[dict]) -> Path:
    width, height = int(config.get("width", 1080)), int(config.get("height", 1920))
    fps = int(config.get("fps", 30))
    jobs = [{
        "id": story["id"],
        "html": str(story_dir(config, story) / f"{story['id']}.html"),
        "out": str(story_dir(config, story) / "frames"),
        "startTime": 0, "count": story["frame_count"], "fps": fps,
        "width": width, "height": height,
    } for story in stories]
    path = resolve(config.get("work_dir", "work"), ROOT) / "capture_jobs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def capture(config: dict, stories: list[dict], only: str | None) -> None:
    build_ring(config)
    jobs = write_capture_jobs(config, stories)
    command = ["node", str(ROOT / "scripts" / "capture_batch.mjs"), "--jobs", str(jobs)]
    if only:
        command += ["--only", only]
    work = resolve(config.get("work_dir", "work"), ROOT)
    run(command, ROOT, work / "capture.log")

    for story in stories:
        if only and story["id"] != only:
            continue
        frames = story_dir(config, story) / "frames"
        for index in range(story["frame_count"]):
            path = frames / f"frame_{index:05d}.png"
            if not path.exists():
                die(f"{story['id']}: missing frame {index}")
            with Image.open(path) as image:
                if image.mode != "RGBA":
                    image.convert("RGBA").save(path)


def compose(config: dict, story: dict) -> Path:
    directory = story_dir(config, story)
    base = directory / "base.mp4"
    web = directory / "web.mp4"
    picture = directory / "picture.mp4"
    temporary = directory / f"{story['name']}_mux.mp4"
    total = story["frame_count"]
    ffmpeg = tool(config.get("ffmpeg", "ffmpeg"))
    fps = int(config.get("fps", 30))
    width, height = int(config.get("width", 1080)), int(config.get("height", 1920))

    # --- web layer over the base footage ------------------------------------
    web_filter = directory / "web_filter.txt"
    drift = (story.get("rhythm") or {}).get("beat")
    base_chain = "[0:v]setpts=PTS-STARTPTS"
    if drift:
        # subtle handheld drift keeps still live footage measurable every 1.5s
        base_chain += (
            f",scale={width + 68}:{height + 120}:flags=lanczos,"
            f"crop={width}:{height}:x='(iw-{width})/2+14*sin(2*PI*t/2.6)':"
            f"y='(ih-{height})/2+14*cos(2*PI*t/2.9)'"
        )
    web_filter.write_text(
        base_chain + ",format=rgba[base];\n"
        f"[1:v]setpts=PTS-STARTPTS,scale={width}:{height},format=rgba[web];\n"
        f"[base][web]overlay=0:0:eof_action=repeat:shortest=0,setpts=N/({fps}*TB),format=yuv444p[vout]",
        encoding="utf-8",
    )
    run([ffmpeg, "-hide_banner", "-y", "-i", str(base), "-framerate", str(fps), "-start_number", "0",
         "-i", "frames/frame_%05d.png", "-filter_complex_script", str(web_filter), "-map", "[vout]", "-an",
         "-fps_mode", "passthrough", "-frames:v", str(total), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "6", "-pix_fmt", "yuv444p", "-video_track_timescale", "15360", str(web)],
        directory, directory / "web.log")

    # --- PIP + burned subtitles --------------------------------------------
    pip = config.get("pip", {})
    pip_size = int(pip.get("size", 340))
    pip_x, pip_y = int(pip.get("x", 604)), int(pip.get("y", 1010))
    crop_x, crop_y, crop_w, crop_h = pip.get("crop", [120, 260, 720, 720])
    circle = "if(lte((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2),(W/2)*(W/2)),255,0)"
    ranges = story["pip_ranges"]

    filters = ["[0:v]setpts=PTS-STARTPTS,format=rgba[vweb]"]
    if len(ranges) == 1:
        filters.append("[1:v]setpts=PTS-STARTPTS,format=rgba[p0src]")
    else:
        outputs = "".join(f"[p{index}src]" for index in range(len(ranges)))
        filters.append(f"[1:v]setpts=PTS-STARTPTS,format=rgba,split={len(ranges)}{outputs}")
    filters.append("[2:v]scale=1080:1920,format=rgba[ring]")
    enable_all = "+".join(f"between(t,{start:.3f},{end - 0.001:.3f})" for start, end in ranges)
    filters.append(f"[vweb][ring]overlay=0:0:enable='{enable_all}'[vr]")

    current = "vr"
    for index, (start, end) in enumerate(ranges):
        length = end - start
        fade_out = max(0.0, length - 0.16)
        filters.append(
            f"[p{index}src]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
            f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={pip_size}:{pip_size},format=rgba,"
            f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{circle}',"
            f"fade=t=in:st=0:d=0.16:alpha=1,fade=t=out:st={fade_out:.3f}:d=0.16:alpha=1,"
            f"setpts=PTS+{start:.3f}/TB[p{index}]"
        )
        output = f"v{index}"
        filters.append(
            f"[{current}][p{index}]overlay={pip_x}:{pip_y}:eof_action=pass:"
            f"enable='between(t,{start:.3f},{end - 0.001:.3f})'[{output}]"
        )
        current = output
    filters.append(f"[{current}]subtitles=captions.ass,format=yuv420p[vout]")

    filter_path = directory / "final_filter.txt"
    filter_path.write_text(";\n".join(filters), encoding="utf-8")
    run([ffmpeg, "-hide_banner", "-y", "-i", str(web), "-i", str(base),
         "-loop", "1", "-framerate", str(fps), "-i", str(build_ring(config)),
         "-filter_complex_script", str(filter_path), "-map", "[vout]", "-an",
         "-frames:v", str(total), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-video_track_timescale", "15360", str(picture)],
        directory, directory / "final.log")

    mux_video, mux_audio = picture, directory / "audio.m4a"
    if story.get("embed_cover"):
        cover_tall = directory / "cover_tall.png"
        if not cover_tall.exists():
            die(f"{story['id']}: cover_tall.png missing, run --stage covers first")
        intro = directory / "intro.mp4"
        run([ffmpeg, "-hide_banner", "-y", "-loop", "1", "-framerate", str(fps), "-t", "0.5",
             "-i", str(cover_tall), "-vf", f"scale={width}:{height},format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p",
             "-video_track_timescale", "15360", str(intro)], directory, directory / "intro.log")
        concat_file = directory / "concat_intro.txt"
        concat_file.write_text(
            f"file '{intro.as_posix()}'\nfile '{picture.as_posix()}'\n", encoding="utf-8")
        joined = directory / "picture_intro.mp4"
        run([ffmpeg, "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
             "-c", "copy", str(joined)], directory, directory / "concat.log")

        lead_audio = directory / "audio_lead.m4a"
        run([ffmpeg, "-hide_banner", "-y", "-f", "lavfi", "-t", "0.5",
             "-i", "anullsrc=r=48000:cl=stereo", "-i", "audio.m4a",
             "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[a]", "-map", "[a]",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(lead_audio)],
            directory, directory / "audio_lead.log")
        mux_video, mux_audio = joined, lead_audio

    run([ffmpeg, "-hide_banner", "-y", "-i", str(mux_video), "-i", str(mux_audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart", str(temporary)],
        directory, directory / "mux.log")

    output_dir = resolve(config.get("output_dir", "output"), ROOT)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{story['name']}.mp4"
    shutil.copy2(temporary, output)
    return output


def qa(config: dict, story: dict, output: Path) -> dict:
    directory = story_dir(config, story)
    ffmpeg = tool(config.get("ffmpeg", "ffmpeg"))
    ffprobe = tool(config.get("ffprobe", "ffprobe"))
    info = probe(ffprobe, output)
    video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in info["streams"] if stream["codec_type"] == "audio")

    result = subprocess.run([ffmpeg, "-v", "error", "-i", str(output), "-f", "null", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    (directory / "qa" / "decode.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0 or result.stdout.strip():
        die(f"{story['id']}: decode errors\n{result.stdout[-2000:]}")

    embed = 0.5 if story.get("embed_cover") else 0.0
    expected_frames = story["frame_count"] + (EMBED_FRAMES if embed else 0)
    expected_duration = story["duration"] + embed

    shots = []
    for index, time in enumerate(story.get("qa_times", [])):
        target = directory / "qa" / f"qa_{index:02d}.jpg"
        run([ffmpeg, "-hide_banner", "-y", "-ss", f"{time + embed:.3f}", "-i", str(output),
             "-frames:v", "1", "-q:v", "2", str(target)], directory)
        shots.append(target)

    if shots:
        thumb_w, thumb_h = 270, 480
        sheet = Image.new("RGB", (thumb_w * 4, thumb_h * 2), (28, 29, 26))
        for index, shot in enumerate(shots[:8]):
            with Image.open(shot) as image:
                thumb = image.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            sheet.paste(thumb, ((index % 4) * thumb_w, (index // 4) * thumb_h))
        sheet.save(directory / "qa" / "contact.jpg", quality=90)

    report = {
        "id": story["id"], "output": str(output),
        "width": video.get("width"), "height": video.get("height"),
        "fps": video.get("r_frame_rate"), "nb_frames": int(video.get("nb_frames", 0)),
        "video_duration": float(video.get("duration", 0)),
        "audio_codec": audio.get("codec_name"), "audio_rate": audio.get("sample_rate"),
        "audio_channels": audio.get("channels"), "audio_duration": float(audio.get("duration", 0)),
        "expected_frames": expected_frames, "expected_duration": expected_duration,
        "decode_clean": True,
    }
    if report["nb_frames"] != expected_frames:
        die(f"{story['id']}: frame count {report['nb_frames']} != {expected_frames}")
    if abs(report["video_duration"] - expected_duration) > 0.05:
        die(f"{story['id']}: duration {report['video_duration']} != {expected_duration}")
    if abs(report["audio_duration"] - expected_duration) > 0.05:
        die(f"{story['id']}: audio duration {report['audio_duration']} != {expected_duration}")

    (directory / "qa" / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def cover_size(config: dict) -> tuple[int, int]:
    width, height = int(config.get("width", 1080)), int(config.get("height", 1920))
    return width, round(width * 4 / 3)


def build_cover_bg(config: dict, story: dict, tall: bool = False) -> Path:
    directory = story_dir(config, story)
    ffmpeg = tool(config.get("ffmpeg", "ffmpeg"))
    width, height = int(config.get("width", 1080)), int(config.get("height", 1920))
    cover_w, cover_h = cover_size(config)
    target = directory / ("cover_bg_tall.jpg" if tall else "cover_bg.jpg")
    time = story.get("cover", {}).get("time", (story.get("qa_times") or [0])[0])
    if not target.exists():
        if tall:
            vf = f"scale={width}:{height}"
        else:
            offset = max(0, (height - cover_h) // 2)
            vf = f"crop={cover_w}:{cover_h}:0:{offset}"
        run([ffmpeg, "-hide_banner", "-y", "-ss", f"{time:.3f}", "-i", str(directory / "base.mp4"),
             "-frames:v", "1", "-vf", vf, "-q:v", "2", str(target)],
            directory, directory / f"cover_bg{'_tall' if tall else ''}.log")
    return target


def build_covers(config: dict, stories: list[dict], only: str | None) -> None:
    work = resolve(config.get("work_dir", "work"), ROOT)
    output_dir = resolve(config.get("output_dir", "output"), ROOT)
    cover_dir = resolve(config.get("cover_dir", str(output_dir / "covers")), ROOT)
    cover_dir.mkdir(parents=True, exist_ok=True)
    cover_w, cover_h = cover_size(config)

    selected = [story for story in stories if not only or story["id"] == only]
    jobs = []
    for story in selected:
        directory = story_dir(config, story)
        cover = story.get("cover") or {}
        for tall, width, height in ((False, cover_w, cover_h), (True, int(config.get("width", 1080)), int(config.get("height", 1920)))):
            suffix = "_tall" if tall else ""
            payload = {
                "id": story["id"], "name": story["name"], "tall": tall,
                "issue": cover.get("issue", ""), "issueLine": cover.get("issueLine", ""),
                "kicker": cover.get("kicker", ""), "title": cover.get("title", []),
                "lines": cover.get("lines", []),
                "footCn": cover.get("footCn", ""), "footEn": cover.get("footEn", ""),
                "theme": story.get("theme", {}),
                "bg": build_cover_bg(config, story, tall).as_uri(),
            }
            template = (ROOT / "assets" / "cover_magazine.html").read_text(encoding="utf-8")
            html = template.replace("__COVER_JSON__", json.dumps(payload, ensure_ascii=False))
            html_path = directory / f"{story['id']}_cover{suffix}.html"
            html_path.write_text(html, encoding="utf-8")
            jobs.append({
                "id": story["id"] + suffix, "html": str(html_path),
                "out": str(directory / f"cover{suffix}.png"),
                "name": story["name"], "width": width, "height": height, "tall": tall,
            })

    jobs_path = work / "cover_jobs.json"
    jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    run(["node", str(ROOT / "scripts" / "capture_cover.mjs"), "--jobs", str(jobs_path)],
        ROOT, work / "covers.log")

    for story in selected:
        directory = story_dir(config, story)
        if not (directory / "cover.png").exists():
            die(f"{story['id']}: cover.png missing")
        shutil.copy2(directory / "cover.png", cover_dir / f"{story['name']}.png")


def main() -> None:
    parser = argparse.ArgumentParser(description="Vertical short-video batch editor")
    parser.add_argument("--stage", required=True,
                        choices=["prepare", "media", "covers", "capture", "render", "all"])
    parser.add_argument("--only", default=None, help="story id, e.g. v01")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        die(f"config not found: {config_path}. Copy config.example.json to config.json")
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))

    stories = load_stories(config)
    selected = [story for story in stories if not args.only or story["id"] == args.only]
    if not selected:
        die(f"no story matched --only {args.only}")

    if args.stage in ("prepare", "all"):
        for story in selected:
            path = prepare(config, story)
            print(f"[prepare] {story['id']} -> {path}")
    if args.stage in ("media", "all"):
        for story in selected:
            build_media(config, story)
            print(f"[media] {story['id']} ready")
    if args.stage in ("covers", "all"):
        build_covers(config, stories, args.only)
        print("[covers] done")
    if args.stage in ("capture", "all"):
        capture(config, stories, args.only)
        print("[capture] done")
    if args.stage in ("render", "all"):
        if not (ROOT / "node_modules" / "playwright-core").exists():
            print("[warn] node_modules missing, run: npm install", file=sys.stderr)
        for story in selected:
            directory = story_dir(config, story)
            if not (directory / "picture.mp4").exists():
                capture(config, stories, story["id"])
            output = compose(config, story)
            report = qa(config, story, output)
            print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
