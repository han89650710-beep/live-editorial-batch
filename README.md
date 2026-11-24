# 直播切片 AI 剪辑流水线（live-editorial-batch）

把一场长口播（直播回放、访谈、课程）做成可直接发布的竖屏短视频：
封面入片头、花字跟读、1.5 秒视觉节拍、真人/页面交替，全部由一份 JSON 配置驱动，本地离线跑。

## 它能做什么

- 从长视频里切出 45–60 秒的高价值片段，按 30fps 精确对齐
- 用网页模板做花字与版式，无头 Chrome 逐帧渲染后合成（不是录屏，是逐帧确定性的）
- 花字时间对齐到「词」，不会出现「画面先说出答案、人还没讲到」
- 用可测量的方式保证画面每 1.5 秒变化一次
- 生成 3:4 发布封面 + 9:16 片头封面，片头封面写入视频前 0.5 秒
- 全流程断言 + QA，不合格直接报错，不会偷偷产出一条烂片

## 它不能做什么

- 不是一键成片：需要你写一份 story.json（约 100 行，有示例可抄）
- 不做自动选段、不做多机位、不做人物跟踪
- 只处理竖屏 9:16 单人镜头
- 不内置语音识别模型（可选装 faster-whisper，或导入现成 SRT）

## 安装

```bash
# 1. 依赖检查（会逐项告诉你缺什么）
python scripts/doctor.py

# 2. 安装缺失项
npm install                        # playwright-core
pip install -r requirements.txt    # Pillow
# 可选：pip install faster-whisper

cp config.example.json config.json # 然后改 source 路径
```

系统依赖：ffmpeg / ffprobe、Node.js 18+、Google Chrome（或设置环境变量 `CHROME_PATH`）。

## 三步跑通

```bash
# 0. 生成 36 秒合成示例素材（无版权风险）
python scripts/make_demo_clip.py

# 1. 跑完整流程
python scripts/build_batch.py --stage all --only demo01

# 2. 看成片
#    output/demo01_run_the_pipeline.mp4
#    output/covers/demo01_run_the_pipeline.png
```

换成自己的素材：

```bash
# 词级转写（二选一）
python scripts/transcribe.py 我的视频.mp4 -o transcript.json
python scripts/transcribe.py --srt 我的字幕.srt -o transcript.json

# 复制示例配置，改 segments / captions / scenes
cp demo/stories/demo01.json stories/v01.json
python scripts/build_batch.py --stage all --only v01
```

## 目录结构

```
live-editorial-batch/
├── SKILL.md                  # 给 AI agent 的使用说明（英文）
├── README.md                 # 本文件
├── config.example.json       # 路径 / PIP / 字幕样式
├── scripts/
│   ├── build_batch.py        # 五阶段主程序
│   ├── capture_batch.mjs     # 逐帧渲染网页层
│   ├── capture_cover.mjs     # 封面截图
│   ├── transcribe.py         # Whisper 或 SRT → 词级时间戳
│   ├── doctor.py             # 环境自检
│   └── make_demo_clip.py     # 生成示例素材
├── assets/
│   ├── web_motion_batch.html # 花字/版式模板（配置注入）
│   ├── cover_magazine.html   # 封面模板（深/浅两套）
│   └── presets/              # 三套主题：暗色杂志 / 瑞士海报 / 报纸剪报
├── references/
│   ├── story-schema.md       # 字段逐项说明（中文）
│   ├── style-library.md      # 七套风格配方与轮换规则（中文）
│   └── qa-checklist.md       # 人工验收清单（中文）
├── demo/                     # 示例素材与 story
└── output/                   # 成片（gitignore）
```

## 五阶段

| 阶段 | 做什么 | 产物 |
|---|---|---|
| prepare | 注入模板、生成字幕、跑规则断言 | HTML、captions.ass、design.json |
| media | 切片、拼接、音频转 AAC | base.mp4、audio.m4a |
| covers | 抽帧做底图，生成两版封面 | cover.png、cover_tall.png |
| capture | 30fps 逐帧截图 | frame_00000.png … |
| render | 合成、PIP、烧字幕、封面入片头、QA | 成片 mp4 |

## 三条硬规则

1. **封面入片头**：`embed_cover: true` 会在正片前拼 0.5 秒封面，QA 期望帧数 +15、时长 +0.5。
2. **花字跟读**：所有 `*At` 与 `beats[]` 都不得早于口播；主标题必须在场景开始 1.6 秒内出现。
3. **1.5 秒节拍**：内容节点最大间隔 ≤4.5 秒，叠加每 1.5 秒的节拍后最大间隔 ≤1.5 秒，真人段另有 ±14px 手持漂移。

## 风格轮换

`assets/presets/` 有三套可直接用的主题。同一账号连续 5 支不要用同一套；同一批次至少 3 种。
浅色主题必须补齐 8 个颜色键，否则会白底白字。

## 持续集成

`.github/workflows/lint.yml` 在每次 push / PR 时执行：Python 语法检查、所有 JSON 合法性、Node 脚本语法，以及生成示例素材后跑一次 `prepare` 冒烟测试。

## 许可

代码 MIT。ffmpeg、playwright-core、字体分别遵循各自许可，详见 `LICENSE`。
示例素材为程序生成的测试画面，不含任何第三方影像。
