# duomi-nano-banana-pro
## [多米api，](https://duomiapi.com/type/all)是可以生图、音乐、视频的稳定接口，价格很低。
## 欢迎通过这个链接注册我有返佣
## https://duomiapi.com/user/register?cps=oxFljTjF

## 本skill用Claude code，其他agent也通用。
<img width="1476" height="1231" alt="image" src="https://github.com/user-attachments/assets/1c3072fa-612b-48ca-bd74-4e53343b5e28" />



一个 [Claude Code](https://claude.com/claude-code) Skill：通过 [duomiapi.com](https://duomiapi.com) 用一句提示词生成 / 编辑 AI 图片和视频。

| 能力 | 子命令 | 模型 |
|---|---|---|
| 文生图、参考图编辑、透明背景、自定义尺寸（含 4K） | `image` | gpt-image-2 / 2.5-flare / 2.5-sunburst / 2.6-flare / 2.6-sunburst |
| Gemini nano-banana 文生图、改图（1K / 2K / 4K） | `nano` | gemini-2.5-flash-image / gemini-3-pro-image-preview |
| VEO 3.1 视频（固定 8 秒，720p / 1080p / 4k） | `video` | veo3.1-fast / veo3.1-pro |
| 本地文件上传到 Cloudinary，拿公网 URL | `upload` | — |
| 手动查询任务 | `query` | — |

脚本只用 Python 3 标准库，无需 `pip install`。流程是：提交任务 → 轮询 → 下载到本地 → 在 stdout 打印文件路径。

## 安装

把本仓库克隆到 Claude Code 的 skills 目录：

```bash
git clone <本仓库地址> ~/.claude/skills/nano-banana-pro
```

重启 Claude Code 后，直接对它说"生成一张……"、"把这张图改成……"、"生成一段视频……"即可触发。

## 配置密钥

密钥**不要**写进仓库或 `SKILL.md`。

**1. Duomi API Key（必需）**，二选一：

```bash
# 方式一：文件（推荐）
mkdir -p ~/.config/duomi
printf '%s' '你的DuomiKey' > ~/.config/duomi/key
chmod 600 ~/.config/duomi/key
```

```bash
# 方式二：环境变量（改完需重启终端 / Claude 应用）
export DUOMI_API_KEY="你的DuomiKey"
```

**2. Cloudinary（可选）**：只有当 `--image` 传的是**本地文件路径**时才需要，用于自动上传换成公网 URL。写入 `~/.config/duomi/cloudinary.env`：

```
CLOUDINARY_CLOUD_NAME=你的cloud_name
CLOUDINARY_API_KEY=你的key
CLOUDINARY_API_SECRET=你的secret
```

```bash
chmod 600 ~/.config/duomi/cloudinary.env
```

也可以用同名环境变量。使用签名上传，不依赖上传预设，文件会放在 `duomi/` 目录下。

## 命令行用法

```bash
S=~/.claude/skills/nano-banana-pro/scripts/duomi.py

# gpt-image 文生图
python3 $S image "一只戴墨镜的柴犬，电影感" --size 16:9 --quality high

# gpt-image 参考图编辑（URL 或本地路径，可重复 --image）
python3 $S image "换成穿红色外套的女性" --image ./a.png

# 透明背景
python3 $S image "产品贴纸风格的咖啡杯" --background transparent

# 4K 横图 / 指定新模型
python3 $S image "雪山日出，电影感" --resolution 4k --ratio 16:9 --quality high
python3 $S image "产品海报" --model gpt-image-2.6-sunburst --size 3:4

# nano-banana 文生图 / 改图（有 --image 自动走 edit 接口）
python3 $S nano "黄昏的郊区庭院" --aspect-ratio 16:9 --image-size 2K
python3 $S nano "改成真实照片风格" --image ./cartoon.png

# 视频
python3 $S video "海边日出，镜头缓慢推进" --aspect-ratio 16:9 --quality 720p
python3 $S video "人物走向镜头" --image ./first.png --generation-type 'FIRST&LAST'

# 只看请求体，不调用 API、不花钱
python3 $S image "test" --dry-run
```

通用选项：

| 选项 | 说明 |
|---|---|
| `--out DIR` | 下载目录，默认 `~/Documents/duomi_output` |
| `--webp` | 转 WebP（image / nano，需要 `pip install pillow`） |
| `--dry-run` | 只打印请求，不调用 |
| `--timeout` / `--interval` | 轮询超时 / 间隔（秒） |

## 参数限制（摘自官方文档）

- **image**：
  - `--size` 可用 `auto`、`1024x1024`、`1792x1024`、`1024x1792` 或比例（`16:9`、`9:16`、`4:3` 等）；自定义 `WxH` 两边都要能被 16 整除，每边 16–3840，总像素 655,360–8,294,400，脚本会先本地校验。
  - `--resolution 1k|2k|4k` + `--ratio`：按长边 1024 / 2048 / 3840 自动算出合法尺寸，超出像素预算时等比缩小（`4k`+`16:9` → 3840x2160，`4k`+`1:1` → 2880x2880）。
  - `--extra '{"callback_url":"..."}'`：额外字段原样并入请求体（官方文档示例里出现过 `callback_url`、`oversea`、`output_format` 等，但接口说明未正式定义，属未验证用法）。
  - 提示词最长 5000 字符。
- **nano**：`--image-size` 的 K 必须大写；参考图最多 10 张，只支持 URL（传本地路径会自动上传）。
- **video**：时长固定 8 秒；`REFERENCE` 模式最多 3 张图，且不支持 9:16；`FIRST&LAST` 可传 1–2 张图。

## 实测情况

| 功能 | 结果 | 大致耗时 |
|---|---|---|
| image 文生图 | 通过 | 约 80 秒 |
| image 参考图编辑 | 通过 | 约 4 分钟 |
| nano 文生图 | 通过 | 约 45 秒 |
| nano 改图（本地图自动上传） | 通过 | 约 20 秒 |
| video 文生视频（veo3.1-fast, 720p） | 通过，输出 1280×720、8 秒 | 约 3 分钟 |
| video `REFERENCE` 模式 | 一次测试失败，服务端返回"可用渠道已尝试，本轮未发起新的请求"，未能确认原因 | 约 6 分钟后报错 |
| video `FIRST&LAST` 模式 | 未测 | — |

## 注意

- 这些调用会产生费用，批量生成或使用 4k / high 前请先确认数量。
- 接口偶尔会因服务端算力问题失败（提示"未知原因……请稍后重试"），重试一次通常即可。
- 上传到 Cloudinary 的图片，任何拿到 URL 的人都能打开，涉及隐私的素材请留意。
- 各接口的进度字段 `progress` 在任务完成前基本一直是 0，不能用来估算剩余时间。

## 文件结构

```
SKILL.md          Skill 定义（触发条件、用法，供 Claude 读取）
scripts/duomi.py  命令行脚本
README.md         本说明
```
