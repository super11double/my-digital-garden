#!/usr/bin/env python3
"""
generate_index.py — 紧急隐私修正版：仅列出 frontmatter 中 share: true 的笔记（默认）

特性要点：
- 默认只显示带 `share: true` 的笔记（frontmatter），避免意外公开私密笔记
- 支持 --include-private 覆盖（管理员模式）
- 保留先前的健壮特性：原子写入、备份轮换、frontmatter title、URL 编码开关、dry-run、verbose 等
- 优先使用 frontmatter 中的 `dg-permalink` 作为对外链接（如果存在），并将索引指向已发布页面的友好路径（不强制 .html）
- 生成与 index.html 对应的 notes.json，以便前端 JS 读取笔记列表
"""
from pathlib import Path
import argparse
import urllib.parse
import html
import os
import sys
import json
import time
import unicodedata
import re
import shutil
import tempfile

# 默认配置（可通过 CLI 覆盖）
DEFAULT_CONFIG = {
    "ignore_basenames": ["generate_index.py", "README.md", "index.md", "index.html", ".DS_Store"],
    "ignore_dirs": [".git", "node_modules", ".venv", "venv", ".obsidian", ".trash", "Templates", "attachments"],
    "extensions": [".md"],
    "encode_urls": True,
    "output": "index.html",
    "json_output": "notes.json",   # 新增：生成的 JSON 文件名
    "title": "我的知识库",
    "backup": True,
    "max_backups": 5,
    "cache_file": ".generate_index_cache.json",
    "public_only": True,   # 核心：默认只列出 share: true 的笔记
}

# --- Helpers ---
def normalize_path(p: Path) -> Path:
    parts = [unicodedata.normalize('NFC', part) for part in p.parts]
    return Path(*parts)

def parse_frontmatter(path: Path) -> dict:
    """
    简单解析 YAML frontmatter（开头以 --- 到下一个 ---）
    返回 dict（key 小写化）
    """
    try:
        text = path.read_text(encoding='utf-8')
    except Exception:
        return {}
    if not text.startswith('---'):
        return {}
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.S)
    if not m:
        return {}
    block = m.group(1)
    data = {}
    for line in block.splitlines():
        if ':' not in line:
            continue
        key, val = line.split(':', 1)
        key = key.strip().lower()
        val = val.strip()
        # strip surrounding quotes
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        data[key] = val
    return data

def frontmatter_share_true(path: Path) -> bool:
    """
    识别 frontmatter 中 share 字段：
    - 返回 True 当字段存在且其值属于 true-like（true, yes, 1, on）
    - 返回 False 否则（包括无 frontmatter / 无 share 字段）
    """
    fm = parse_frontmatter(path)
    v = fm.get('share')
    if v is None:
        return False
    v_norm = str(v).strip().lower()
    return v_norm in ('true', 'yes', '1', 'on')

def read_frontmatter_title(path: Path) -> str:
    fm = parse_frontmatter(path)
    t = fm.get('title', '')
    return unicodedata.normalize('NFC', t).strip() if t else ''

def is_ignored(p: Path, root: Path, ignore_basenames, ignore_dirs) -> bool:
    if p.name in ignore_basenames:
        return True
    for part in p.relative_to(root).parts:
        if part in ignore_dirs:
            return True
    return False

def scan_markdown_files(root: Path, cfg: dict, include_private: bool, verbose=False):
    files = []
    excluded_by_privacy = 0
    exts = set(cfg.get("extensions", [".md"]))
    for p in root.rglob("*"):
        try:
            if p.is_file() and p.suffix.lower() in exts:
                np = normalize_path(p)
                if is_ignored(np, root, cfg["ignore_basenames"], cfg["ignore_dirs"]):
                    continue
                if cfg.get("public_only", True) and not include_private:
                    # 只有当 frontmatter share: true 时才包含
                    if not frontmatter_share_true(np):
                        excluded_by_privacy += 1
                        continue
                files.append(np)
        except OSError:
            if verbose:
                print(f"⚠️  无法访问 {p}, 跳过")
    return files, excluded_by_privacy

def make_href(rel_path: Path, encode: bool) -> str:
    url_path = str(rel_path).replace(os.sep, '/')
    if encode:
        return urllib.parse.quote(url_path, safe='/%23%25%5B%5D@!$&\'()*+,;=')
    else:
        return url_path

def html_item_line(href: str, display: str, mtime: float = None) -> str:
    disp = html.escape(display)
    if mtime:
        t = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))
        return f'        <li><a href="{href}">{disp}</a> <small>({t})</small></li>'
    else:
        return f'        <li><a href="{href}">{disp}</a></li>'

def atomic_write(path: Path, content: str):
    dir = path.parent
    fd, tmpname = tempfile.mkstemp(prefix=path.name, dir=str(dir))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmpname, str(path))
    finally:
        if os.path.exists(tmpname):
            try:
                os.remove(tmpname)
            except Exception:
                pass

def rotate_backups(path: Path, max_backups: int, verbose=False):
    parent = path.parent
    prefix = path.name + ".bak-"
    existing = sorted([p for p in parent.iterdir() if p.name.startswith(prefix)], key=lambda p: p.name)
    while len(existing) > max_backups:
        rm = existing.pop(0)
        try:
            rm.unlink()
            if verbose:
                print(f"🧹 删除旧备份 {rm}")
        except Exception:
            pass

# --- Main ---
def build_index(root: Path, cfg: dict, args: argparse.Namespace) -> int:
    files, excluded_privacy = scan_markdown_files(root, cfg, include_private=args.include_private, verbose=args.verbose)
    if args.verbose:
        print(f"🔎 Found {len(files)} public markdown files (excluded_by_privacy={excluded_privacy}) under {root}")

    out_path = root / cfg["output"]
    out_json_path = root / cfg.get("json_output", "notes.json")

    # build items (prefer frontmatter title)
    items = []
    for p in files:
        rel = p.relative_to(root)
        title = read_frontmatter_title(p)
        display = title if title else str(rel.with_suffix('')).replace(os.sep, '/')

        # 优先使用 frontmatter 中的 dg-permalink（如果存在），否则回退到与页面同名的路径（去掉后缀）
        fm = parse_frontmatter(p)
        permalink = ''
        if fm:
            permalink = fm.get('dg-permalink', '') or fm.get('dg_permalink', '') or ''
            permalink = permalink.strip() if isinstance(permalink, str) else ''
        if permalink:
            # 确保没有前导斜杠，但不强制追加 .html — 使用作者在 frontmatter 中指定的 permalink 原样
            permalink = permalink.lstrip('/')
            href_path = permalink
        else:
            # 不带扩展名的链接（例如 notes/爱情），更适合 GitHub Pages 或静态站点的路由
            href_path = str(rel.with_suffix('')).replace(os.sep, '/')

        href = make_href(Path(href_path), cfg.get("encode_urls", True))
        try:
            mtime = p.stat().st_mtime
        except Exception:
            mtime = None
        items.append({"path": p, "rel": str(rel), "display": display, "href": href, "mtime": mtime})

    # sort by path
    items.sort(key=lambda x: x["rel"].casefold())

    # build HTML
    lines = []
    for it in items:
        lines.append(html_item_line(it["href"], it["display"], mtime=it["mtime"]))
    list_html = "\n".join(lines) + ("\n" if lines else "")

    html_intro = ""
    if not list_html:
        html_intro = "<p><em>当前未找到公开的笔记（默认只显示 frontmatter: share: true 的笔记）。</em></p>"

    content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>{html.escape(cfg.get('title','我的知识库'))}</title>
</head>
<body>
    <h1>{html.escape(cfg.get('title','我的知识库'))}</h1>
    {html_intro}
    <ul>
{list_html}    </ul>
</body>
</html>
"""

    # prepare JSON payload for frontend
    # 包含基本字段：href, title (display), rel, mtime (秒，或 null)
    json_items = []
    for it in items:
        json_items.append({
            "href": it["href"],
            "title": it["display"],
            "rel": it["rel"],
            "mtime": int(it["mtime"]) if it["mtime"] is not None else None
        })
    json_content = json.dumps(json_items, ensure_ascii=False, indent=2)

    if args.dry_run:
        print("=== DRY RUN ===")
        print(f"Will write: {out_path} ({len(items)} items listed).")
        print(f"Will write JSON: {out_json_path} ({len(json_items)} items).")
        print(f"Excluded by privacy rule: {excluded_privacy} files.")
        return 0

    # backup index.html
    if out_path.exists() and cfg.get("backup", True):
        ts = time.strftime('%Y%m%d-%H%M%S')
        bak = out_path.with_name(out_path.name + ".bak-" + ts)
        try:
            shutil.copy2(out_path, bak)
            if args.verbose:
                print(f"🔁  备份旧的 {out_path} -> {bak}")
            rotate_backups(out_path, cfg.get("max_backups", 5), verbose=args.verbose)
        except Exception as e:
            print("⚠️  备份失败：", e)

    # write index.html
    try:
        atomic_write(out_path, content)
    except Exception as e:
        print("❌ 写入失败：", e)
        return 2

    # backup notes.json
    if out_json_path.exists() and cfg.get("backup", True):
        ts = time.strftime('%Y%m%d-%H%M%S')
        bakj = out_json_path.with_name(out_json_path.name + ".bak-" + ts)
        try:
            shutil.copy2(out_json_path, bakj)
            if args.verbose:
                print(f"🔁  备份旧的 {out_json_path} -> {bakj}")
            rotate_backups(out_json_path, cfg.get("max_backups", 5), verbose=args.verbose)
        except Exception as e:
            if args.verbose:
                print("⚠️  JSON 备份失败：", e)

    # write notes.json
    try:
        atomic_write(out_json_path, json_content)
    except Exception as e:
        print("❌ 写入 notes.json 失败：", e)
        return 2

    print(f"✅ 已生成 {out_path}，列出 {len(items)} 个公开笔记（排除 {excluded_privacy} 个私密笔记）。")
    print(f"✅ 已生成 {out_json_path}（供前端读取）。")
    return 0

def parse_args(argv):
    p = argparse.ArgumentParser(description="Generate index.html from markdown files (public-only by default).")
    p.add_argument("--root", "-r", default=".", help="repo root (default: current dir)")
    p.add_argument("--output", "-o", help="output file (overrides config)")
    p.add_argument("--no-encode", action="store_true", help="disable URL encoding")
    p.add_argument("--include-private", action="store_true", help="INCLUDE private notes (override default public-only behavior) — use with caution")
    p.add_argument("--dry-run", action="store_true", help="do not write files, just show actions")
    p.add_argument("--verbose", "-v", action="store_true", help="verbose output")
    return p.parse_args(argv)

def main(argv):
    args = parse_args(argv)
    root = Path(args.root).resolve()

    # load defaults (简单)
    cfg = dict(DEFAULT_CONFIG)
    if args.no_encode:
        cfg["encode_urls"] = False
    if args.output:
        cfg["output"] = args.output

    # core privacy: public_only default is True; args.include_private overrides it
    args.include_private = bool(args.include_private)

    return build_index(root, cfg, args)

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
