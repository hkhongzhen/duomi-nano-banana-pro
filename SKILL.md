---
name: "duomi-nano-banana-pro"
description: "通过 duomiapi.com 生成和编辑 AI 图片与视频：gpt-image-2 系列、Gemini nano-banana、VEO 3.1 视频。用户要求生图、改图、图生图、换人物、透明背景、生成视频、文生视频、首尾帧视频，或提到 nano-banana / gpt-image / veo / duomi 时调用。"
---

# Duomi 图片 / 视频生成

所有调用都走脚本 `scripts/duomi.py`（仅标准库）。脚本负责：提交任务 → 轮询 → 下载到本地 → 在 stdout 打印文件路径。**不要自己手写 curl 或自己循环轮询。**

## 前置：API Key

Key 从环境变量 `DUOMI_API_KEY` 读取，或从文件 `~/.config/duomi/key` 读取。绝不把 Key 写进本文件、代码或回复里。缺 Key 时脚本会报错，此时让用户自行设置，不要向用户索要 Key。

## 选哪个子命令

| 需求 | 命令 | 默认模型 |
|---|---|---|
| 通用生图 / 参考图编辑 / 透明背景 / 自定义尺寸 | `image` | gpt-image-2 |
| 想用 Gemini nano-banana（文生图、改图、1K/2K/4K） | `nano` | gemini-2.5-flash-image |
| 视频（文生视频、首尾帧、参考图） | `video` | veo3.1-fast |

用户没指定时：图片默认用 `image`；明确提到 nano-banana / Gemini 才用 `nano`。

## 用法

```bash
S=~/.claude/skills/nano-banana-pro/scripts/duomi.py

# 文生图
python3 $S image "一只戴墨镜的柴犬，电影感" --size 16:9 --quality high

# 参考图编辑（URL 或本地路径，可重复 --image）
python3 $S image "换成穿红色外套的女性" --image https://example.com/a.png

# 透明背景
python3 $S image "产品贴纸风格的咖啡杯" --background transparent

# 4K 横图（自动算出 3840x2160）/ 指定新模型
python3 $S image "雪山日出，电影感" --resolution 4k --ratio 16:9 --quality high
python3 $S image "产品海报" --model gpt-image-2.6-sunburst --size 3:4

# nano-banana 文生图 / 改图（有 --image 自动走 edit 接口）
python3 $S nano "黄昏的郊区庭院，石板小径" --aspect-ratio 16:9 --image-size 2K
python3 $S nano "把天空改成日落" --image https://example.com/a.jpg

# 视频（固定 8 秒）
python3 $S video "海边日出，镜头缓慢推进" --aspect-ratio 16:9 --quality 1080p
python3 $S video "人物走向镜头" --image https://example.com/first.png --generation-type FIRST\&LAST
```

通用选项：`--out DIR`（默认 `~/Documents/duomi_output`）、`--webp`（image/nano，需 Pillow）、`--dry-run`（只打印请求体，不花钱）、`--timeout`、`--interval`。

输出：每行一个本地文件路径。拿到路径后告诉用户，并按需用 Read 查看图片。

## 参数要点

**image（gpt-image-2 系列）**
- 模型（`--model`）：`gpt-image-2`（默认）、`gpt-image-2.5-flare`（替代 image 2 的新模型，速度约快一倍）、`gpt-image-2.5-sunburst`（更高级）、`gpt-image-2.6-flare`、`gpt-image-2.6-sunburst`
- 尺寸二选一：
  - `--size`：`auto`、`1024x1024`、`1792x1024`、`1024x1792`、比例（`1:1 3:2 2:3 16:9 9:16 1:2 2:1 4:3 3:4 5:4 4:5`），或自定义 `WxH`。自定义会先本地校验：宽高都能被 16 整除、每边 16–3840、总像素 655,360–8,294,400，不合法直接报错，不会浪费一次调用
  - `--resolution 1k|2k|4k` 加 `--ratio`（默认 1:1）：脚本按长边 1024/2048/3840 自动算出合法尺寸，超出像素预算时等比缩小。例：`4k` + `16:9` → 3840x2160；`4k` + `1:1` → 2880x2880；`4k` + `3:4` → 2480x3312。不能和 `--size` 同时用
- `--quality`：low / medium（默认）/ high；`--background`：auto / opaque / transparent
- `--extra '{"字段":值}'`：把任意额外字段原样并入请求体（文档示例里出现过 `callback_url`、`oversea`、`output_format`、`frame_count`、`frame_duration_ms` 等，但接口说明里没有正式定义，属于未验证的用法）
- 提示词最长 5000 字符，超长会本地报错

**nano**
- 模型：`gemini-2.5-flash-image`、`gemini-3-pro-image-preview`
- `--aspect-ratio`：`1:1 2:3 3:2 3:4 4:3 4:5 5:4 9:16 16:9 21:9`，留空为 auto
- `--image-size`：`1K 2K 4K`（K 必须大写）；`--image` 最多 10 张，仅 URL，不支持 base64
- 文生图和改图是两个不同接口，脚本已按是否有 `--image` 自动选择

**video（VEO 3.1）**
- 模型：`veo3.1-fast`、`veo3.1-pro`；时长固定 8 秒
- `--aspect-ratio`：16:9 / 9:16；`--quality`：720p / 1080p / 4k
- `--generation-type`：`TEXT`（文生视频）、`FIRST&LAST`（首尾帧，1–2 张图）、`REFERENCE`（参考元素，最多 3 张，**不支持 9:16**）；不指定时无图为 TEXT，有图为 FIRST&LAST
- 视频耗时长，默认超时 1200 秒；超时后可用 `python3 $S query /v1/videos/tasks/<任务id>` 手动查询（图片任务用 `query <任务id>`）

## 注意

- `--image` 可以直接给本地路径：脚本自动签名上传到 Cloudinary（目录 `duomi/`）换成 URL，再提交。单独上传用 `python3 $S upload 文件...`。
- Cloudinary 凭证读环境变量 `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET`，或文件 `~/.config/duomi/cloudinary.env`（每行 `KEY=VALUE`）。不要在回复里显示这些值。
- 上传的图片会公开可访问（URL 即可打开），涉及隐私或未发布的素材先跟用户确认。
- 这些调用会产生费用：批量生成或高分辨率（4k、high）前先跟用户确认数量。
- 任务失败时脚本会退出并打印服务端返回的内容，原样转告用户，不要无限重试。
- 想要干净图片时，在提示词里加"无文字、无水印"。
- 提示词不用翻译，中英文都可以。
