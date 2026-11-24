---
name: live-editorial-batch
description: Turn long talking-head footage into packaged vertical short videos with synced captions, a 1.5s visual rhythm, and live/page alternation. Use when the user asks for 直播切片, 口播短视频批量剪辑, 网页花字包装, 1.5秒节拍, or a repeatable short-video pipeline. Do not use for simple trimming with no packaging.
---

# Live Editorial Batch

A deterministic, config-driven pipeline that turns long vertical talking-head footage
(e.g. a livestream recording) into packaged short videos:

- word-level caption sync — on-screen text never appears before it is spoken
- a web-motion "flowers" layer rendered frame by frame in headless Chrome
- a measurable 1.5-second visual rhythm (asserted, not judged by eye)
- full-screen live cuts alternating with structured pages
- a magazine cover embedded into the first 0.5s of every video
- the circular PIP auto-centered on the speaker's face (no manual crop guessing)
- a planning step that splits the transcript into sentences, keeps the ones the topic
  needs, and reorders them into a new script before any cutting happens

Length follows the content: there is no 45–60s target. Cut every sentence the argument
needs and stop when it is complete; a 30s clip and a 90s clip are equally valid.

Everything runs locally. No cloud rendering, no upload of footage.

## Prerequisites

Check first, then install only what is missing:

```bash
python scripts/doctor.py          # reports every missing dependency
npm install                       # playwright-core
pip install -r requirements.txt   # Pillow
```

Required: Python 3.9+, ffmpeg/ffprobe, Node.js, Google Chrome (or set `CHROME_PATH`).
Optional: `faster-whisper` for local transcription; otherwise import an SRT.

## Quickstart

```bash
cp config.example.json config.json      # then edit source / paths
python scripts/make_demo_clip.py        # 36s synthetic clip, no copyright risk
python scripts/build_batch.py --stage all --only demo01
```

Output lands in `output/`, covers in `output/covers/`.

With real footage:

```bash
# 1) word-level transcript (whisper or existing subtitles)
python scripts/transcribe.py my_video.mp4 -o transcript.json
python scripts/transcribe.py --srt my_captions.srt -o transcript.json

# 2) split the transcript into sentences, pick by topic, reorder into a new script
python scripts/plan_from_transcript.py --transcript transcript.json \
    --topic "九块九,毛利,获客" --id v01 --source my_video.mp4 --out stories/v01.json

# 3) rewrite the placeholder pages, then run
python scripts/build_batch.py --stage all --only v01
```

`plan_from_transcript.py` is the "拆解逐字稿、重新排列" step: every sentence becomes its
own segment, `--order relevance` ranks them by the topic keywords and lays them out in a
new order, `--order timeline` keeps the speaking order. `--max-seconds` is off by default;
only pass it when the client asks for a hard cap.

## Pipeline

| Stage | Input | Output |
|---|---|---|
| `prepare` | story JSON | injected HTML, `captions.ass`, `design.json`, rule assertions |
| `media` | source + time ranges | `base.mp4`, `audio.m4a` |
| `covers` | `base.mp4` + cover config | 3:4 publish cover, 9:16 intro cover |
| `capture` | HTML | one RGBA PNG per frame at 30fps |
| `render` | frames + base + cover | composited video, burned subtitles, QA |

Stages are dependent and must run in this order. `render` also runs QA and fails loudly.

## Hard rules (enforced by `prepare`)

1. **Cover into the intro** — `"embed_cover": true` prepends 0.5s (15 frames) of the tall
   cover; QA expects `frames + 15` and `duration + 0.5`.
2. **Caption sync** — every `*At` / `beats[]` value is relative to the scene start and must
   not precede the spoken word. `headAt` must be ≤ 1.6s or `prepare` aborts.
3. **1.5s visual rhythm** — `"rhythm": {"beat": 1.5}` requires: content gap ≤ 4.5s,
   merged content+tick gap ≤ 1.5s, plus handheld drift on live footage.
4. **Live / page alternation** — at least 4 `live` scenes, `dark` scenes never adjacent,
   live share 18–32%.
5. **Deterministic render** — `renderAt(t)` must not use `Date`, `Math.random`, or
   time-based animation libraries.

Details and field-by-field documentation: `references/story-schema.md`
(Chinese original; English mirror at `references/story-schema.en.md`).
Style presets and rotation rules: `references/style-library.md` (`style-library.en.md`).
Manual acceptance list: `references/qa-checklist.md` (`qa-checklist.en.md`).

## Scene types

`hook` (opening claim), `verdict` (closing card), `list`, `steps`, `versus`, `chain`,
`stat`, `quote`, and `live` (full-screen footage, no overlay except burned subtitles).

## Style presets

Three ready themes ship in `assets/presets/`:

| Preset | Character | Best for |
|---|---|---|
| `dark-magazine` | near-black, fine grid, serif headline, neon accent | mechanism, long causal chains |
| `swiss-poster` | paper white, giant sans, strict grid, one red | opinions, judgments, conclusions |
| `broadsheet` | cream paper, serif masthead, double rules, red stamp | exposés, myth-busting |

Copy a preset's `theme` object into the story. Light themes require the extra keys
(`rule`, `inkSoft`, `inkFaint`, `ghost`, `subInk`, `itemInk`, `gridInk`, `breath`,
`mode: "light"`), otherwise text renders white on white.

Never reuse one style for more than 5 consecutive videos; use at least 3 styles per batch.

## PIP (circular cut-out)

`pip.crop` is a square `[x, y, side, side]` cut from the source frame and scaled into the
circle. Leave it out and `prepare` detects the speaker's face on the segments that make up
the video, takes the median face center and caches the result in `work/<id>/pip_auto.json`,
so the face sits in the middle of the circle. Set `pip.crop` in a story only to override the
detection; `pip.auto_crop: false` disables it, `pip.crop_side` (default 720) caps the crop
resolution. Run `scripts/auto_pip.py --video src.mp4 --out pip.json` to see the numbers.

## Common failures

- Frames are cached: after editing a template, delete `work/<id>/frames/*.png`.
- `covers` needs `media` first; `render` needs `covers` first.
- The last caption must end ≥ 0.02s before the total duration.
- With `live` scenes present the stage must stay transparent; that is also why two
  `dark` scenes may not touch each other.
- On light themes, a missing theme key produces invisible text.

## Limits

This is not a one-click product. The authoring step is a JSON story file. The skill
assumes vertical 9:16 footage and one speaker; it does not do multi-cam switching or
object tracking. Sentence selection in `plan_from_transcript.py` is keyword-based — read
the draft order before rendering and move sentences that break the argument.
