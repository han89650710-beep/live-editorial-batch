# QA checklist

Automated assertions run at the end of `--stage render`. After they pass, do the manual pass.

## Automated (hard failures)

- Frame count = duration × 30 + 15 when a cover is embedded
- Video/audio duration difference ≤ 0.05s
- H.264 / yuv420p / AAC 48kHz stereo
- Zero decode errors across the whole file

## Manual (5 checks)

1. **First 0.5s** — cover is complete, headline does not wrap, sub-line is not covered.
2. **Around every scene cut** — no accidental flash of full-screen footage.
3. **Caption sync** — sample 5–8 points; on-screen text must not precede the spoken word.
4. **1.5s rhythm** — downscale to 108×192 grayscale at 10fps and measure frame
   differences; page scenes ≥ 2.0, live scenes ≥ 1.5, pass rate 100% (rework below 95%).
5. **PIP** — present on pages, absent on live cuts, never "person plus a second person".

## Measuring the rhythm

```python
import subprocess
import numpy as np

def frames(path, fps=10, w=108, h=192):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vf",
           f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w).astype(np.int16)

data = frames("output/demo01_run_the_pipeline.mp4")
diff = np.abs(np.diff(data, axis=0)).mean(axis=(1, 2))
# take the max per 1.5s window and check it against the threshold
```

## Richness score (100 points, publish at ≥ 80)

| Dimension | Points | Target |
|---|---:|---|
| Content density | 20 | ≥ 10 content nodes per minute |
| Cut density | 20 | ≥ 1 scene change per 10s; live share 18–32% |
| Rhythm | 20 | ≥ 95% of 1.5s windows pass |
| Layout hierarchy | 20 | ≥ 3 levels per page, bilingual or numbered |
| Shot and decoration | 20 | PIP composition varies; texture ≤ 8%; ≤ 3 colours |
