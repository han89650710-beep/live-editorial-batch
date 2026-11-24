# live-editorial-batch

English ｜ [中文](README.md)

![demo](docs/demo.gif)

Turn long talking-head footage (livestream recordings, interviews, lectures) into
publish-ready vertical short videos. A single JSON config drives everything:
cover embedded into the first 0.5s, captions that never run ahead of speech, a
measurable 1.5-second visual rhythm, and full-screen live cuts alternating with
structured pages. Runs entirely on your machine.

## What it does

- Splits the transcript into sentences, keeps the ones the topic needs, reorders them
  into a new script, then cuts at frame-accurate 30fps offsets. Length follows the
  content — there is no 45–60s target
- Auto-centers the circular PIP on the speaker's face (YuNet, median across sampled
  frames), so nobody hand-tunes the crop box
- Renders the text/graphics layer as HTML in headless Chrome, one deterministic
  screenshot per frame, then composites it over the footage
- Aligns on-screen text to individual words, so a caption never reveals an answer
  before the speaker says it
- Enforces a 1.5s visual rhythm with measurements instead of eyeballing
- Produces a 3:4 publish cover and a 9:16 cover embedded into the video intro
- Fails loudly: every rule is an assertion, plus a final QA gate

## What it does not do

- Not a one-click product: you author a `story.json` (~100 lines, examples included)
- Sentence picking is keyword-based, not semantic — review the draft order; no multi-cam
  switching or person tracking
- Vertical 9:16 single-speaker footage only
- No bundled speech model — optional `faster-whisper`, or import an existing SRT

## Install

```bash
python scripts/doctor.py            # reports anything missing
npm install                         # playwright-core
pip install -r requirements.txt     # Pillow
# optional: pip install faster-whisper

cp config.example.json config.json  # then edit `source`
```

System requirements: Python 3.9+, ffmpeg/ffprobe, Node.js 18+, Google Chrome
(or set `CHROME_PATH`).

## Updating

This folder is a copy of the GitHub repository. Check before starting a new video:

```bash
python scripts/update.py --check    # compare local and remote versions
python scripts/update.py            # apply a newer release (--deps reinstalls packages)
```

The updater replaces code files only: `config.json`, `stories/`, `work/`, `output/` and
`node_modules/` are never touched, so a finished cut survives the update. The agent checks
before a new video, reports a newer release in one sentence, and updates **only after you
agree** — never silently, never mid-cut. A git clone is
fast-forwarded with `git pull --ff-only`; a zip install downloads the latest archive and
refreshes code. Offline simply reports that the check failed — rendering still works.


## Run the demo

```bash
python scripts/make_demo_clip.py                  # 36s synthetic clip, no copyright risk
python scripts/build_batch.py --stage all --only demo01
# output/demo01_run_the_pipeline.mp4
```

## Use your own footage

```bash
# word-level transcript (pick one)
python scripts/transcribe.py input.mp4 -o transcript.json
python scripts/transcribe.py --srt captions.srt -o transcript.json

# split into sentences, rank by topic, reorder into a draft story
python scripts/plan_from_transcript.py --transcript transcript.json \
    --topic "price,margin,acquisition" --id v01 --source input.mp4 --out stories/v01.json

python scripts/build_batch.py --stage all --only v01   # rewrite the placeholder pages first
```

`--order relevance` (default) reorders by keyword score, `--order timeline` keeps the
speaking order. `--max-seconds` is off by default; pass it only for a hard client cap.

## Pipeline

| Stage | Does | Produces |
|---|---|---|
| `prepare` | injects config into the template, writes subtitles, runs rule assertions | HTML, `captions.ass`, `design.json` |
| `media` | cuts, concatenates, encodes audio | `base.mp4`, `audio.m4a` |
| `covers` | grabs a frame, renders both covers | `cover.png`, `cover_tall.png` |
| `capture` | screenshots the web layer at 30fps | `frame_00000.png…` |
| `render` | composites, PIP, burns subtitles, prepends cover, QA | final mp4 |

## Hard rules

1. **Cover in the intro** — `embed_cover: true` prepends 0.5s (15 frames); QA expects
   `frames + 15` and `duration + 0.5`.
2. **Caption sync** — every `*At` / `beats[]` value must not precede the spoken word;
   a page headline must appear within 1.6s.
3. **1.5s rhythm** — content gaps ≤ 4.5s, merged with 1.5s ticks ≤ 1.5s, plus handheld
   drift on live footage.

## PIP and face centering

The circular PIP uses `pip.crop` (`[x, y, side, side]`, a square cut from the source frame)
scaled into the circle. Leave `pip.crop` out and `prepare` samples every segment of the
story, detects the face, takes the median center and caches it in `work/<id>/pip_auto.json`,
so the face sits in the middle of the circle. Set `pip.crop` in a story to override;
`pip.auto_crop: false` disables detection, `pip.crop_side` (default 720) caps the crop size.
Check one clip with `python scripts/auto_pip.py --video input.mp4 --out pip.json`.

## Length

There is no fixed duration. How many sentences the topic needs decides the runtime;
30s and 90s are both fine. Never pad a cut to hit a number.

## Scene types

`hook`, `verdict`, `list`, `steps`, `versus`, `chain`, `stat`, `quote`, `live`.

## Style presets

`assets/presets/`: `dark-magazine`, `swiss-poster`, `broadsheet`. Never use one style for
more than 5 consecutive videos; at least 3 styles per batch. Light themes require the
extra colour keys documented in `SKILL.md`, otherwise text renders white on white.

## Documentation

- `SKILL.md` — agent-facing workflow and constraints
- `references/story-schema.en.md` — every field (`story-schema.md` is the Chinese original)
- `references/style-library.en.md` — seven style recipes and rotation rules
- `references/qa-checklist.en.md` — manual acceptance list and rhythm measurement

## License

MIT. ffmpeg, playwright-core and fonts keep their own licenses — see `LICENSE`.
The demo clip is a generated test pattern and contains no third-party footage.
