# story.json field reference

One video = one JSON file inside `stories/` (or `config.stories_dir`).
All times are seconds. "Relative" means relative to that scene's `start`.

## Top level

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique id, same as the file name (`v01`). Used by `--only` |
| `name` | yes | Output file name without extension |
| `version` | no | `"2.0"` enables all strict rules (cover intro, live alternation, rhythm assertions) |
| `rhythm` | no | `{"beat": 1.5}` enables the 1.5s rhythm assertions |
| `embed_cover` | no | `true` prepends a 0.5s cover to the video |
| `source` | no | Overrides `config.source`; absolute or relative to the package root |
| `segments` | yes | Source ranges, e.g. `[[120.5, 174.9]]`; multiple ranges are concatenated |
| `captions` | yes | Caption list, see below |
| `scenes` | yes | Scene list; must tile the whole timeline with no gaps |
| `cover` | no | Cover config, see below |
| `qa_times` | no | Frame-check timestamps (video time, excluding the 0.5s cover) |
| `chapter_footer` | no | Right-hand footer text |
| `theme` | no | Theme variables, see "Theme" |

## captions

```json
{"seg": 0, "s": 120.5, "e": 123.2, "text": "first line\nsecond line"}
```

- `seg`: index into `segments`
- `s` / `e`: absolute source time, must stay inside that segment
- `text`: `\n` breaks the line; the last caption must end ≥ 0.02s before the total duration

## scenes

```json
{
  "key": "turn", "type": "versus", "bg": "dark", "start": 20.9, "end": 28.6,
  "kicker": "THE REAL COST", "chapter": "03 / 07", "ghost": "03",
  "english": "MAKE VS SELL",
  "headline": ["Deciding to start", "is not the hard part"],
  "left":  {"label": "Making",  "en": "MAKING",  "items": ["2-3 months"], "beats": [3.6]},
  "right": {"label": "Selling", "en": "SELLING", "items": ["Acquisition"], "beats": [6.9]},
  "leftAt": 3.4, "rightAt": 5.4, "midAt": 4.5,
  "kickerAt": 0.08, "headAt": 0.15, "englishAt": 0.3,
  "note": "Selling, acquiring, servicing", "noteSub": "this is where people stall", "noteAt": 7.4
}
```

### Types

| type | Layout | Key fields |
|---|---|---|
| `hook` | giant headline + sub + tag/rule | `headline` `sub` `tag` `note` `ghost` |
| `verdict` | same as hook, used to close | same |
| `list` | checklist cards | `items[{label,en}]` `beats[]` |
| `steps` | numbered steps, current one highlighted | `items[{label,en}]` `beats[]` |
| `versus` | two columns + VS badge | `left` `right` `leftAt` `rightAt` `midAt` |
| `chain` | causal chain with connectors | `items[{label,en}]` `beats[]` |
| `stat` | oversized number | `big` `bigUnit` `label` `sub` |
| `quote` | quote card + key line | `quote` `sub` |
| `live` | full-screen footage, no overlay at all | `start`/`end` only |

### Timing fields

| Field | Default | Meaning |
|---|---|---|
| `kickerAt` | 0.06 | top-left category label |
| `headAt` | 0.14 | headline — must be ≤ 1.6 |
| `englishAt` | 0.28 | decorative English line |
| `subAt` | 0.38 | sub line |
| `ruleAt` / `tagAt` / `noteAt` | per type | rule / tag / note |
| `beats[]` | +0.12 each | item reveal times; rendered at `beat - 0.05` |
| `leftAt` / `rightAt` / `midAt` | 0.36 / 0.54 / 0.92 | comparison columns and VS badge |
| `bigAt` / `labelAt` | 0.42 / 0.66 | stat page |

`left.beats` / `right.beats` control items inside comparison columns.

## cover

```json
"cover": {
  "issue": "13",
  "issueLine": "STORY FIRST / 2026",
  "kicker": "STORE ECONOMICS",
  "title": ["9.9 traffic", "then what?"],
  "lines": ["Margin must land at 10-17%", "First-tier stores sell social status", "Drinks alone: stop early"],
  "time": 25.0
}
```

- `time` must fall inside a `live` scene, otherwise the cover background is a static page
- the last `title` line is rendered in the accent colour
- keep `lines` to 3 items, each ≤ 16 characters (CJK) / ~40 characters (Latin)

## Theme

```json
"theme": {
  "bg": "#0B1518", "panel": "#122225", "text": "#EDF6F3", "muted": "#8FAEAA",
  "accent": "#FF5C8A", "head": "Microsoft YaHei", "body": "Microsoft YaHei",
  "panelSolid": "rgba(11,21,24,.94)", "accentInk": "#3B0A1B"
}
```

Light themes must also provide:

```json
"rule": "rgba(20,20,20,.18)", "inkSoft": "rgba(20,20,20,.66)", "inkFaint": "rgba(20,20,20,.45)",
"ghost": "rgba(20,20,20,.06)", "subInk": "#2B2B2B", "itemInk": "#141414",
"gridInk": "#141414", "breath": "#000000", "mode": "light"
```

`mode: "light"` also switches the cover to the paper layout; `skin: "broadsheet"` adds
paper texture and serif headlines.

## Validation performed by `prepare`

1. Scenes not contiguous, or not covering the whole timeline
2. Caption outside its segment, or past the total duration
3. `headAt > 1.6`
4. Content gap > 4.5s, or merged content+tick gap > 1.5s
5. 2.0 only: fewer than 4 `live` scenes, adjacent `dark` scenes, live share outside 18-32%
