#!/usr/bin/env python3
"""duomiapi.com 命令行：生图 / 改图 / 视频。仅用标准库。

子命令:
  image  gpt-image-2 系列（文生图、参考图编辑）  POST /v1/images/generations?async=true
  nano   Gemini nano-banana（文生图 / 改图）      POST /api/gemini/nano-banana[-edit]
  video  VEO 3.1 视频                              POST /v1/videos/generations
  upload 本地文件 -> Cloudinary，打印 URL（--image 给本地路径时会自动调用）

流程: 提交 -> 轮询 -> 下载到本地 -> stdout 打印文件路径（每行一个）。
API Key: 环境变量 DUOMI_API_KEY，或文件 ~/.config/duomi/key。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

BASE = "https://duomiapi.com"


def get_key():
    key = os.environ.get("DUOMI_API_KEY", "").strip()
    if not key:
        p = Path.home() / ".config" / "duomi" / "key"
        if p.exists():
            key = p.read_text().strip()
    if not key:
        sys.exit("缺少 API Key：请设置环境变量 DUOMI_API_KEY，或写入 ~/.config/duomi/key")
    return key


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def http(method, path, key, body=None, retries=3):
    url = path if path.startswith("http") else BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", key)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "duomi-skill/1.0")
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code < 500:  # 4xx 不重试
                sys.exit(f"HTTP {e.code}: {msg}")
            last = f"HTTP {e.code}: {msg}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = str(e)
        time.sleep(2 * (i + 1))
    sys.exit(f"请求失败: {last}")


def find_urls(obj, exts=None):
    """递归收集响应里的 http(s) 链接。"""
    out = []
    if isinstance(obj, str):
        if obj.startswith("http") and (not exts or urlparse(obj).path.lower().endswith(exts)):
            out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out += find_urls(v, exts)
    elif isinstance(obj, list):
        for v in obj:
            out += find_urls(v, exts)
    return list(dict.fromkeys(out))


def get_id(resp):
    if isinstance(resp.get("id"), str):
        return resp["id"]
    d = resp.get("data")
    if isinstance(d, dict):
        for k in ("task_id", "id"):
            if d.get(k):
                return d[k]
    sys.exit(f"提交失败，响应里没有任务 id: {json.dumps(resp, ensure_ascii=False)[:500]}")


def poll(path, key, timeout, interval, exts=None):
    """轮询直到完成，返回结果 URL 列表。"""
    start = time.time()
    while True:
        r = http("GET", path, key)
        # nano-banana 的状态嵌在 r["data"]["state"]；gpt-image/veo 在顶层 r["state"]
        inner = r.get("data") if isinstance(r.get("data"), dict) and "state" in r["data"] else r
        state = str(inner.get("state") or "").lower()
        prog = inner.get("progress")
        r = inner if inner is not r else r
        log(f"[{int(time.time()-start)}s] state={state or '?'} progress={prog}")
        if state in ("error", "failed", "fail", "failure"):
            sys.exit(f"任务失败: {r.get('msg') or r.get('message') or ''} | {json.dumps(r, ensure_ascii=False)[:600]}")
        if not state:
            sys.exit(f"无法识别的查询响应（没有 state 字段）: {json.dumps(r, ensure_ascii=False)[:600]}")
        if state in ("succeeded", "success", "completed", "complete", "done"):
            urls = find_urls(r.get("data", r), exts)
            if not urls:
                sys.exit(f"任务成功但没找到结果链接: {json.dumps(r, ensure_ascii=False)[:800]}")
            return urls
        if time.time() - start > timeout:
            sys.exit(f"轮询超时（{timeout}s）。可稍后用: duomi.py query {path}")
        time.sleep(interval)


def download(url, out_dir, prefix, idx, webp=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(urlparse(url).path).suffix or ".bin"
    dest = out_dir / f"{prefix}_{idx}{ext}"
    req = urllib.request.Request(url, headers={"User-Agent": "duomi-skill/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if webp and ext.lower() in (".png", ".jpg", ".jpeg"):
        try:
            from PIL import Image
            w = dest.with_suffix(".webp")
            Image.open(dest).save(w, "WEBP", quality=80)
            dest.unlink()
            dest = w
        except ImportError:
            log("未安装 Pillow，跳过 webp 转换（pip install pillow）")
    return dest


def finish(urls, args, kind):
    prefix = f"{kind}_{time.strftime('%Y%m%d_%H%M%S')}"
    for i, u in enumerate(urls, 1):
        print(download(u, Path(args.out), prefix, i, getattr(args, "webp", False)).resolve())
    for u in urls:
        log("URL:", u)


def run_task(submit_path, body, args, poll_tpl, kind, exts=None):
    key = get_key()
    if args.dry_run:
        print(json.dumps({"POST": submit_path, "body": body}, ensure_ascii=False, indent=2))
        return
    tid = get_id(http("POST", submit_path, key, body))
    log("task id:", tid)
    urls = poll(poll_tpl.format(id=tid), key, args.timeout, args.interval, exts)
    finish(urls, args, kind)


def cloudinary_creds():
    """环境变量优先，其次 ~/.config/duomi/cloudinary.env (KEY=VALUE 每行一个)。"""
    names = ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    vals = {n: os.environ.get(n, "").strip() for n in names}
    p = Path.home() / ".config" / "duomi" / "cloudinary.env"
    if p.exists():
        for line in p.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() in vals and not vals[k.strip()]:
                vals[k.strip()] = v.strip().strip("\"'")
    if not all(vals.values()):
        sys.exit("缺少 Cloudinary 凭证：请设置 CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET 环境变量，"
                 "或写入 ~/.config/duomi/cloudinary.env")
    return vals["CLOUDINARY_CLOUD_NAME"], vals["CLOUDINARY_API_KEY"], vals["CLOUDINARY_API_SECRET"]


def upload_cloudinary(path):
    """签名上传本地文件到 Cloudinary，返回 secure_url。"""
    import hashlib
    import mimetypes
    import uuid
    cloud, ck, cs = cloudinary_creds()
    p = Path(path).expanduser()
    if not p.is_file():
        sys.exit(f"本地文件不存在: {p}")
    ts = str(int(time.time()))
    folder = "duomi"
    sig = hashlib.sha1(f"folder={folder}&timestamp={ts}{cs}".encode()).hexdigest()
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (("api_key", ck), ("timestamp", ts), ("folder", folder), ("signature", sig)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{p.name}"\r\n'
                  f"Content-Type: {mime}\r\n\r\n").encode() + p.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{cloud}/auto/upload", data=b"".join(parts), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "duomi-skill/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"Cloudinary 上传失败 HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"Cloudinary 连接失败: {e}")
    url = res.get("secure_url")
    if not url:
        sys.exit(f"Cloudinary 响应缺少 secure_url: {json.dumps(res)[:300]}")
    log(f"已上传: {p.name} -> {url}")
    return url


def resolve_images(items, dry_run=False):
    """http(s) 链接原样使用；本地路径自动上传 Cloudinary 换成 URL。"""
    out = []
    for it in items or []:
        if it.startswith(("http://", "https://")):
            out.append(it)
        elif dry_run:
            out.append(f"<将上传本地文件: {it}>")
        else:
            out.append(upload_cloudinary(it))
    return out


def cmd_upload(a):
    for f in a.files:
        print(upload_cloudinary(f))


IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
VID_EXT = (".mp4", ".mov", ".webm")


GPT_RATIOS = ("1:1", "3:2", "2:3", "16:9", "9:16", "1:2", "2:1", "4:3", "3:4", "5:4", "4:5")
GPT_PRESETS = ("1024x1024", "1792x1024", "1024x1792")
MIN_PX, MAX_PX, MAX_SIDE = 655_360, 8_294_400, 3840
RES_LONG_EDGE = {"1k": 1024, "2k": 2048, "4k": 3840}


def check_wh(w, h):
    """官方限制：每边 16–3840 且能被 16 整除；总像素 655,360–8,294,400。"""
    if w % 16 or h % 16:
        sys.exit(f"尺寸 {w}x{h} 不合法：宽高都必须能被 16 整除")
    if not (16 <= w <= MAX_SIDE and 16 <= h <= MAX_SIDE):
        sys.exit(f"尺寸 {w}x{h} 不合法：每条边必须在 16–{MAX_SIDE}")
    if not (MIN_PX <= w * h <= MAX_PX):
        sys.exit(f"尺寸 {w}x{h} 不合法：总像素 {w*h:,} 须在 {MIN_PX:,}–{MAX_PX:,}")


def size_from_resolution(res, ratio):
    """按长边（1k=1024 / 2k=2048 / 4k=3840）和比例算出合法 WxH；超出像素预算时等比缩放。"""
    import math
    rw, rh = (int(x) for x in ratio.split(":"))
    long_edge = RES_LONG_EDGE[res]
    if rw >= rh:
        w, h = long_edge, long_edge * rh / rw
    else:
        h, w = long_edge, long_edge * rw / rh
    px = w * h
    if px > MAX_PX:
        k = math.sqrt(MAX_PX / px)
        w, h = w * k, h * k
    elif px < MIN_PX:
        k = math.sqrt(MIN_PX / px)
        w, h = w * k, h * k
    # 先向下取 16 的倍数；若因此低于下限则向上取
    fw, fh = int(w // 16) * 16, int(h // 16) * 16
    if fw * fh < MIN_PX:
        fw, fh = math.ceil(w / 16) * 16, math.ceil(h / 16) * 16
    check_wh(fw, fh)
    return f"{fw}x{fh}"


def resolve_gpt_size(a):
    if a.resolution:
        if a.size and a.size != "auto":
            sys.exit("--resolution 与 --size 不能同时使用（--resolution 需搭配 --ratio）")
        return size_from_resolution(a.resolution, a.ratio)
    s = a.size
    if not s or s == "auto" or s in GPT_RATIOS or s in GPT_PRESETS:
        return s
    if "x" in s:
        try:
            w, h = (int(x) for x in s.lower().split("x"))
        except ValueError:
            sys.exit(f"无法识别的 --size: {s}")
        check_wh(w, h)
        return s
    sys.exit(f"无法识别的 --size: {s}（可用 auto、比例 {'/'.join(GPT_RATIOS)}、或 WxH）")


def cmd_image(a):
    body = {"model": a.model, "prompt": a.prompt, "quality": a.quality, "background": a.background}
    if len(a.prompt) > 5000:
        sys.exit(f"提示词 {len(a.prompt)} 字符，超过 5000 上限")
    size = resolve_gpt_size(a)
    if size:
        body["size"] = size
    if a.extra:
        try:
            extra = json.loads(a.extra)
            assert isinstance(extra, dict)
        except (ValueError, AssertionError):
            sys.exit("--extra 必须是 JSON 对象，例如 '{\"callback_url\": \"https://...\"}'")
        body.update(extra)
    if a.image:
        body["image"] = resolve_images(a.image, a.dry_run)
    run_task("/v1/images/generations?async=true", body, a, "/v1/tasks/{id}", "image", IMG_EXT)


def cmd_nano(a):
    body = {"model": a.model, "prompt": a.prompt, "oversea": True, "image_size": a.image_size}
    if a.aspect_ratio:
        body["aspect_ratio"] = a.aspect_ratio
    if a.image:
        body["image_urls"] = resolve_images(a.image, a.dry_run)
        path = "/api/gemini/nano-banana-edit"
    else:
        path = "/api/gemini/nano-banana"
    run_task(path, body, a, "/api/gemini/nano-banana/{id}", "nano", IMG_EXT)


def cmd_video(a):
    gt = a.generation_type or ("TEXT" if not a.image else "FIRST&LAST")
    if gt == "REFERENCE" and a.aspect_ratio == "9:16":
        sys.exit("REFERENCE 模式暂不支持 9:16")
    if len(a.image or []) > 3:
        sys.exit("最多 3 张参考图")
    body = {"model": a.model, "prompt": a.prompt, "aspect_ratio": a.aspect_ratio,
            "duration": 8, "generation_type": gt, "quality": a.quality}
    if a.image:
        body["image_urls"] = resolve_images(a.image, a.dry_run)
    run_task("/v1/videos/generations", body, a, "/v1/videos/tasks/{id}", "video", VID_EXT)


def cmd_query(a):
    key = get_key()
    path = a.path if a.path.startswith("/") else f"/v1/tasks/{a.path}"
    print(json.dumps(http("GET", path, key), ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, interval, timeout):
        sp.add_argument("prompt")
        sp.add_argument("--image", action="append", help="参考图：URL 或本地路径（自动传 Cloudinary），可重复")
        sp.add_argument("--out", default=str(Path.home() / "Documents" / "duomi_output"), help="下载目录")
        sp.add_argument("--interval", type=float, default=interval)
        sp.add_argument("--timeout", type=int, default=timeout)
        sp.add_argument("--dry-run", action="store_true", help="只打印请求体，不调用 API")

    s = sub.add_parser("image", help="gpt-image-2 系列")
    common(s, 5, 600)
    s.add_argument("--model", default="gpt-image-2",
                   choices=["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst",
                            "gpt-image-2.6-flare", "gpt-image-2.6-sunburst"])
    s.add_argument("--size", help="auto | 比例(16:9 等) | 1024x1024 | 自定义WxH（会校验：被16整除、每边16–3840、总像素655,360–8,294,400）")
    s.add_argument("--resolution", choices=["1k", "2k", "4k"],
                   help="按分辨率档位自动算尺寸（长边 1024/2048/3840），搭配 --ratio；超出像素预算时自动等比缩小")
    s.add_argument("--ratio", default="1:1", choices=list(GPT_RATIOS), help="配合 --resolution 使用，默认 1:1")
    s.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    s.add_argument("--background", default="auto", choices=["auto", "opaque", "transparent"])
    s.add_argument("--extra", help='额外字段 JSON，原样并入请求体，如 \'{"callback_url":"https://..."}\'')
    s.add_argument("--webp", action="store_true")
    s.set_defaults(f=cmd_image)

    s = sub.add_parser("nano", help="Gemini nano-banana")
    common(s, 4, 600)
    s.add_argument("--model", default="gemini-2.5-flash-image",
                   choices=["gemini-2.5-flash-image", "gemini-3-pro-image-preview"])
    s.add_argument("--aspect-ratio", default="")
    s.add_argument("--image-size", default="1K", choices=["1K", "2K", "4K"])
    s.add_argument("--webp", action="store_true")
    s.set_defaults(f=cmd_nano)

    s = sub.add_parser("video", help="VEO 3.1 视频")
    common(s, 10, 1200)
    s.add_argument("--model", default="veo3.1-fast", choices=["veo3.1-fast", "veo3.1-pro"])
    s.add_argument("--aspect-ratio", default="16:9", choices=["16:9", "9:16"])
    s.add_argument("--quality", default="720p", choices=["720p", "1080p", "4k"])
    s.add_argument("--generation-type", choices=["TEXT", "FIRST&LAST", "REFERENCE"])
    s.set_defaults(f=cmd_video)

    s = sub.add_parser("upload", help="上传本地文件到 Cloudinary，打印 URL")
    s.add_argument("files", nargs="+")
    s.set_defaults(f=cmd_upload)

    s = sub.add_parser("query", help="手动查询任务")
    s.add_argument("path", help="任务 id，或完整路径如 /api/gemini/nano-banana/<id>")
    s.set_defaults(f=cmd_query)

    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
