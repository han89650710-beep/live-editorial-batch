# story.json 字段说明

一支视频 = 一个 JSON 文件，放在 `stories/`（或 `config.stories_dir` 指定的目录）。
时间单位统一为秒。所有「相对时间」都相对本场景的 `start`。

## 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 唯一标识，与文件名一致，如 `v01`。`--only v01` 用它筛选 |
| `name` | 是 | 成片文件名（不含扩展名） |
| `version` | 否 | 写 `"2.0"` 开启全部硬规则（封面入片头、真人交替、节拍断言） |
| `rhythm` | 否 | 写 `{"beat": 1.5}` 开启 1.5 秒节拍断言 |
| `embed_cover` | 否 | `true` = 片头插入 0.5 秒封面 |
| `source` | 否 | 覆盖 `config.source`，可写绝对路径或相对包根目录 |
| `segments` | 是 | 源片区间数组，如 `[[120.5, 174.9]]`；多段会自动拼接 |
| `captions` | 是 | 字幕数组，见下 |
| `scenes` | 是 | 场景数组，必须首尾相接覆盖整条时间轴 |
| `cover` | 否 | 封面配置，见下 |
| `qa_times` | 否 | 抽帧验收时间点（相对成片，不含封面 0.5 秒） |
| `chapter_footer` | 否 | 页脚右侧文字 |
| `theme` | 否 | 主题变量，见「主题」 |

## captions

```json
{"seg": 0, "s": 120.5, "e": 123.2, "text": "第一行\n第二行"}
```

- `seg`：第几段（`segments` 的下标）
- `s` / `e`：源片的绝对时间，必须落在该段内
- `text`：`\n` 表示换行；最后一条的 `e` 要比总时长早 0.02 秒，否则报错

## scenes

```json
{
  "key": "turn", "type": "versus", "bg": "dark", "start": 20.9, "end": 28.6,
  "kicker": "最难一步 / THE REAL COST", "chapter": "03 / 07", "ghost": "03",
  "english": "MAKE VS SELL",
  "headline": ["决定做一件事", "难在哪一步？"],
  "left":  {"label": "制作", "en": "MAKING", "items": ["技法，两三个月"], "beats": [3.6]},
  "right": {"label": "营销", "en": "SELLING", "items": ["获客"], "beats": [6.9]},
  "leftAt": 3.4, "rightAt": 5.4, "midAt": 4.5,
  "kickerAt": 0.08, "headAt": 0.15, "englishAt": 0.3,
  "note": "营销、获客、客户服务", "noteSub": "卡住所有人的地方", "noteAt": 7.4
}
```

### 类型

| type | 结构 | 关键字段 |
|---|---|---|
| `hook` | 巨号标题 + 副行 + 标签/红线 | `headline` `sub` `tag` `note` `ghost` |
| `verdict` | 同 hook，收尾用 | 同上 |
| `list` | 勾选卡片 | `items[{label,en}]` `beats[]` |
| `steps` | 编号步骤，高亮当前步 | `items[{label,en}]` `beats[]` |
| `versus` | 左右两列 + VS | `left` `right` `leftAt` `rightAt` `midAt` |
| `chain` | 因果链节点 + 连线 | `items[{label,en}]` `beats[]` |
| `stat` | 巨号数字 | `big` `bigUnit` `label` `sub` |
| `quote` | 引文卡 + 金句条 | `quote` `sub` |
| `live` | 全屏真人，不渲染任何覆盖层 | 只有 `start`/`end` |

### 时间字段

| 字段 | 默认 | 含义 |
|---|---|---|
| `kickerAt` | 0.06 | 左上分类小字 |
| `headAt` | 0.14 | 主标题（必须 ≤ 1.6） |
| `englishAt` | 0.28 | 英文装饰行 |
| `subAt` | 0.38 | 副行 |
| `ruleAt` / `tagAt` / `noteAt` | 见类型 | 红线 / 标签 / 注释 |
| `beats[]` | 递增 0.12 | 条目出现时间；实际渲染 = `beat - 0.05` |
| `leftAt` / `rightAt` / `midAt` | 0.36 / 0.54 / 0.92 | 对比页两列与 VS 圆点 |
| `bigAt` / `labelAt` | 0.42 / 0.66 | 数字页 |

`left.beats` / `right.beats` 控制对比页列内条目时间。

## cover

```json
"cover": {
  "issue": "13",
  "issueLine": "STORY FIRST / 2026",
  "kicker": "门店生意 / STORE ECONOMICS",
  "title": ["九块九引流", "靠什么赚钱"],
  "lines": ["毛利要落在 10% 到 17%", "一线城市都在搞高端社交", "纯靠饮品，尽早止损"],
  "time": 25.0
}
```

- `time` 必须落在某个 `live` 场景内，否则底图是静止页面
- `title` 最后一行会渲染成强调色
- `lines` 建议 3 条，每条 ≤ 16 字

## 主题

```json
"theme": {
  "bg": "#0B1518", "panel": "#122225", "text": "#EDF6F3", "muted": "#8FAEAA",
  "accent": "#FF5C8A", "head": "Microsoft YaHei", "body": "Microsoft YaHei",
  "panelSolid": "rgba(11,21,24,.94)", "accentInk": "#3B0A1B"
}
```

浅色主题必须补：

```json
"rule": "rgba(20,20,20,.18)", "inkSoft": "rgba(20,20,20,.66)", "inkFaint": "rgba(20,20,20,.45)",
"ghost": "rgba(20,20,20,.06)", "subInk": "#2B2B2B", "itemInk": "#141414",
"gridInk": "#141414", "breath": "#000000", "mode": "light"
```

`mode: "light"` 同时让封面切换为白纸版式；`skin: "broadsheet"` 额外开启纸纹与衬线标题。

## 常用校验（prepare 会直接报错）

1. 场景不连续、首尾未覆盖整条时间轴
2. 字幕超出所属段或超过总时长
3. `headAt > 1.6`
4. 内容节点间隔 > 4.5 秒，或叠加节拍后仍 > 1.5 秒
5. 2.0：`live` 少于 4 段、`dark` 相邻、真人占比不在 18–32%
