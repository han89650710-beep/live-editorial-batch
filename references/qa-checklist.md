# QA 验收清单

自动断言通过（`--stage render` 末尾会打印 report）之后，仍然需要人工过一遍。

## 自动断言（不通过直接报错）

- 帧数 = 时长 × 30 +（封面 15 帧）
- 视频/音频时长误差 ≤ 0.05 秒
- 编码：H.264 / yuv420p / AAC 48kHz 双声道
- 全片解码零错误

## 人工验收（5 项）

1. **片头 0–0.5 秒**：封面完整，标题不换行、不压导读。
2. **每个场景切点前后**：没有「全屏真人闪一下」的穿帮。
3. **花字跟读**：抽 5–8 个点，比对画面文字与同帧字幕，文字不得早于口播。
4. **1.5 秒节拍**：用 108×192 灰度、10fps 逐帧差，统计每 1.5 秒窗口的最大帧差。
   - 页面段 ≥ 2.0；真人段成片 ≥ 1.5
   - 达标率要求 100%，低于 95% 返工
5. **PIP**：页面段有、真人段无、无「真人 + 小窗真人」同框；人脸在圆心里，头顶和下巴都留在圆内，不偏左偏右。
6. **文案与时长**：段与段之间接得上（前一句的结论是后一句的前提）；时长取到把话说完整为止，没有为凑时长加的空话。

## 帧差测量（参考实现）

```python
import subprocess, numpy as np

def frames(path, fps=10, w=108, h=192):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vf",
           f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w).astype(np.int16)

data = frames("output/demo01_run_the_pipeline.mp4")
diff = np.abs(np.diff(data, axis=0)).mean(axis=(1, 2))
# 每个 1.5 秒窗口取最大值，检查是否都超过阈值
```

## 丰富度评分（100 分，≥80 才发）

| 维度 | 分值 | 达标线 |
|---|---:|---|
| 内容密度 | 20 | 每分钟内容节点 ≥ 10 个 |
| 切换密度 | 20 | 每 10 秒 ≥ 1 次场景切换；真人 18–32% |
| 节拍达标 | 20 | ≥ 95% 的 1.5 秒窗口达标 |
| 版式层级 | 20 | 每页 ≥ 3 层级 + 中英双语或编号 |
| 镜头与装饰 | 20 | PIP 构图有变化；纹理 ≤ 8%；颜色 ≤ 3 |
