# Packaging style library

Maintenance: append one row per finished video; review every 5 videos.

A style is not a filter. It is a full visual grammar: background, type, hierarchy,
decoration, motion, and cover. Rotate all six together, or the platform still sees the
same template.

## Selection table

| Content type | First choice | Second choice |
|---|---|---|
| Opinions, judgments, strong conclusions | Swiss poster | Kinetic type |
| Exposés, debunking, science, counter-intuitive | Broadsheet | Neo-brutalism |
| Personal experience, stories, memories | Collage / zine | Dark magazine |
| Mechanisms, causal chains | Dark magazine (default) | Swiss poster |
| Data, timelines, comparisons | Broadcast news | Swiss poster |
| One-liners, attitude, emotion | Kinetic type | Neo-brutalism |
| Products, trends, business commentary | Neo-brutalism | Dark magazine |

Never use one style for more than 5 consecutive videos; at least 3 styles per batch.

## 1. Dark magazine (default, `assets/presets/dark-magazine.json`)

- Grammar: near-black ground, fine grid, serif headline, neon accent, issue numbers.
- Use for: mechanism explainers, long causal chains, "newsroom" feel.
- Tokens: `bg #0B1518`, `text #EDF6F3`, accent neon pink/cyan, `head` serif.
- Avoid: several videos in the same hue; it collides with the "vibe knowledge" look.

## 2. Swiss poster (`assets/presets/swiss-poster.json`)

- Grammar: paper white, oversized sans, strict left grid, one saturated colour, no
  rounded corners or shadows.
- Use for: opinions, judgments, conclusions that fit in one sentence.
- Tokens: `bg #F1F0EC`, `text #141414`, `accent #E2231A`, 900-weight headline.
- Layout: small category top-left, issue top-right, two-line headline, 1px rules
  instead of cards.
- Caveat: all 8 light-theme keys are required, or text turns white on white.

## 3. Broadsheet (`assets/presets/broadsheet.json`)

- Grammar: cream paper, full-width serif headline, double rules, red stamp, date bar.
- Use for: exposés, myth-busting, anything that needs "evidence" weight.
- Tokens: `bg #EFE9DC`, `text #17130F`, `accent #B3261E`, `head "Noto Serif SC"`.
- Enable with `theme.skin: "broadsheet"` (paper texture, serif titles, double footer rule).

## 4. Neo-brutalism

- Grammar: hard-edged colour blocks, thick outlines, hard shadows, sticker labels.
- Use for: conflicts, attitude pieces, business commentary.
- Tokens: `bg #F5F1E8`, accents `#FF4D00 / #2F5BFF / #C6FF00`.
- Limit: at most 3 items per page, otherwise it becomes noise.

## 5. Collage / zine

- Grammar: kraft paper, torn edges, tape, paper clips, highlighter tags, Polaroids.
- Use for: personal stories and travel; keep the speaker near the visual centre.
- Avoid: hard data and firm conclusions, it reads unprofessional.

## 6. Broadcast news

- Grammar: red/white bars, lower third, timecode, ticker.
- Use for: news, commentary, timelines, data readouts.
- Tokens: `bg #0E1116`, `accent #D7261E`.

## 7. Kinetic type

- Grammar: word-by-word reveals, keyword colour changes, weight/size jumps on the beat.
- Use for: one-liners, attitude, low information density.
- Limit: no more than 12 characters per screen; one visible change every 1.5s.

## Richness checklist (any style)

1. At least 3 hierarchy levels per page: category / headline / items / note / footer.
2. Bilingual decoration: English never carries information.
3. Numbering: pick two of `01 / 05`, page number, issue number.
4. Texture layer: grid, paper, halftone, scanline — opacity ≤ 8%.
5. Shot layer: change PIP position or size every 2 pages.
6. No more than 3 colours: background, text, accent.

## Visual log (anonymized cases)

| Case | Style | Duration | Live cuts / share | Min 1.5s frame diff | Score | Issue found | Next change |
|---|---|---:|---|---:|---:|---|---|
| A | Dark magazine | 50.2s | 4 / 22% | 1.754 (live) | 92 | PIP never moves | Move/resize PIP every 2 pages |
| B | Swiss poster | 50.9s | 4 / 24% | 4.387 | 88 | Light pages feel empty | Add a bottom info band |
| C | Broadsheet | 55.0s | 6 / 26% | 3.971 | 90 | Closing card only 1.7s | Give it 2.5s or add a tag |

What the three cases taught us:

- Text glow alone leaves still live footage under 1.7; breathing + handheld drift keeps
  it around 4.
- Light styles pop in thumbnails but expose empty space; PIP and captions must fill it.
- A closing card under 2 seconds feels rushed; viewers cannot screenshot it.

## Candidate styles (not yet validated)

- Memphis geometry: saturated shapes with thick outlines, for light science content.
- Halftone pop: dotted portraits with flat blocks, for opinion pieces.
- Minimal whiteboard: hand-drawn line art on white, for step-by-step explainers.

A candidate must ship one sample video passing every gate before joining the library.
