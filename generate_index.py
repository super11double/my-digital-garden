#!/usr/bin/env python3
"""
generate_index.py — 紧急隐私修正版：仅列出 frontmatter 中 share: true 的笔记（默认）

特性要点：
- 默认只显示带 `share: true` 的笔记（frontmatter），避免意外公开私密笔记
- 支持 --include-private 覆盖（管理员模式）
- 保留先前的健壮特性：原子写入、备份轮换、frontmatter title、URL 编码开关、dry-run、verbose 等
- 优先使用 frontmatter 中的 `dg-permalink` 作为对外链接（如果存在），并将索引指向已发布页面的友好路径（不强制 .html）
- 生成与 index.html 对应的 notes.json，以便前端 JS 读取笔记列表

新增：
- 列表显示以文件名（不含 .md 后缀）为准（默认），避免 frontmatter title 覆盖导致意外显示英文或不期望的文本。
- 自动把 Wiki 链接形式 [[目标]] 转成对应笔记的网页链接（如果能解析到目标笔记），让内部引用可点击。
- 避免同名冲突：别名映射优先使用相对路径（不含扩展名），仅在文件名唯一时才把 basename 作为别名。
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
    # display 可能包含 HTML（例如已转换的 [[Wiki]] 链接），如果包含 <a 则认为已安全构造，避免再次转义
    if '<a ' in display or display.strip().startswith('<a'):
        disp = display
    else:
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

# --- Wiki link helpers ---
WIKI_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

def convert_wiki_links_in_text(text: str, alias_map: dict) -> str:
    """
    将文本中的 [[Page]] 或 [[Page|Label]] 转成 HTML 链接（如果能解析到 alias_map）。
    alias_map: {alias: href}
    返回替换后的 HTML 片段
    """
    if not text:
        return text

    def repl(m):
        target = m.group(1).strip()
        label = m.group(2).strip() if m.group(2) else None
        key = target
        href = alias_map.get(key)
        if href is None:
            href = alias_map.get(key.lower())
        if href is None:
            return html.escape(m.group(0))
        display = label if label else target
        return f'<a href="{html.escape(href)}">{html.escape(display)}</a>'

    return WIKI_RE.sub(repl, text)

def convert_wiki_links_to_text(text: str) -> str:
    """
    将 [[Page|Label]] 或 [[Page]] 转成纯文本（用于 JSON title 字段）
    """
    if not text:
        return text
    def repl(m):
        target = m.group(1).strip()
        label = m.group(2).strip() if m.group(2) else None
        return label if label else target
    return WIKI_RE.sub(repl, text)

# --- Main ---
def build_index(root: Path, cfg: dict, args: argparse.Namespace) -> int:
    # Prefer scanning notes/ subfolder if present so index always reflects current notes/ content.
    notes_dir = root / 'notes'
    scan_root = notes_dir if notes_dir.exists() and notes_dir.is_dir() else root

    files, excluded_privacy = scan_markdown_files(scan_root, cfg, include_private=args.include_private, verbose=args.verbose)
    if args.verbose:
        print(f"Found {len(files)} public markdown files (excluded_by_privacy={excluded_privacy}) under {scan_root}")

    out_path = root / cfg["output"]
    out_json_path = root / cfg.get("json_output", "notes.json")

    # build items (使用文件名为主，避免 frontmatter title 覆盖中文文件名)
    items = []
    for p in files:
        # make rel be relative to repo root so JSON paths include 'notes/...' when scanning notes/
        try:
            rel = p.relative_to(root)
        except Exception:
            # fallback to path relative to scan_root if needed
            rel = p.relative_to(scan_root)
            rel = Path('notes') / rel

        filename_only = p.stem
        fm = parse_frontmatter(p)

        # 决定显示文本：使用文件名（不带后缀）。不再优先使用 frontmatter title。
        display_text = unicodedata.normalize('NFC', filename_only)

        # 优先使用 frontmatter 中的 dg-permalink（如果存在），否则回退到与页面同名的路径（去掉后缀）
        permalink = ''
        if fm:
            permalink = fm.get('dg-permalink', '') or fm.get('dg_permalink', '') or ''
            permalink = permalink.strip() if isinstance(permalink, str) else ''
        if permalink:
            permalink = permalink.lstrip('/')
            href_path = permalink
        else:
            # ensure we remove suffix safely and avoid stray trailing dots
            rel_no_ext = str(rel.with_suffix('')).replace(os.sep, '/')
            if rel_no_ext.endswith('.'):
                rel_no_ext = rel_no_ext[:-1]
            # use a directory-style href (trailing slash) so GitHub Pages serves notes/<name>/index.html
            href_path = rel_no_ext.rstrip('.') + '/'

        href = make_href(Path(href_path), cfg.get("encode_urls", True))
        try:
            mtime = p.stat().st_mtime
        except Exception:
            mtime = None
        items.append({"path": p, "rel": str(rel), "display_text": display_text, "href": href, "mtime": mtime, "basename": filename_only})

    # build alias map for wiki links: prefer relative-path keys to avoid collisions
    alias_map = {}
    # count basenames so we only add basename when unique
    basename_counts = {}
    for it in items:
        basename_counts[it['basename']] = basename_counts.get(it['basename'], 0) + 1

    # add rel-path keys (without extension), e.g., "notes/学习"
    for it in items:
        rel_no_ext = str(Path(it['rel']).with_suffix('')).replace(os.sep, '/')
        if rel_no_ext.endswith('.'):
            rel_no_ext = rel_no_ext[:-1]
        alias_map[rel_no_ext] = it['href']
        alias_map[rel_no_ext.lower()] = it['href']

    # add basename keys only when unique
    for it in items:
        b = it['basename']
        if basename_counts.get(b, 0) == 1:
            alias_map[b] = it['href']
            alias_map[b.lower()] = it['href']

    # convert wiki links in display (HTML) and also produce plain text title for JSON
    for it in items:
        it['display_html'] = convert_wiki_links_in_text(it['display_text'], alias_map)
        it['display_plain'] = convert_wiki_links_to_text(it['display_text'])

    # sort by path
    items.sort(key=lambda x: x["rel"].casefold())

    # build HTML
    lines = []
    for it in items:
        # use display_html inside list; html_item_line will avoid double-escaping if it contains <a
        lines.append(html_item_line(it["href"], it.get("display_html", it.get("display_text", "")), mtime=it["mtime"]))
    list_html = "\n".join(lines) + ("\n" if lines else "")

    html_intro = ""
    if not list_html:
        html_intro = "<p id=\"no-notes\"><em>当前未找到公开的笔记（默认只显示 frontmatter: share: true 的笔记）。</em></p>"

    # The generated HTML contains a server-side list as a fallback, but also includes
    # client-side JS which will try to load a modern JSON (notes_modern.json) first and
    # fall back to legacy notes.json if needed. This makes the frontend robust to both
    # older workflows and the newer generator output.
    page_title = html.escape(cfg.get('title','我的知识库'))
    content = """<!DOCTYPE html>
    <html>
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>{PAGE_TITLE}</title>
        <style>
          body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; padding: 1rem; }}
          ul {{ line-height: 1.6; }}
          small {{ color: #666; margin-left: .5rem; }}
        </style>
    </head>
    <body>
        <h1>{PAGE_TITLE}</h1>
        {html_intro}
        <ul id=\"notes-list\">
    {list_html}    </ul>
        
    <script>
    (function(){
      // Try modern file first, then legacy notes.json. Render into #notes-list.
      const listEl = document.getElementById('notes-list');
      const noNotesEl = document.getElementById('no-notes');
        
      function render(items){
        listEl.innerHTML = '';
        if(!items || items.length === 0){
          if(noNotesEl) noNotesEl.style.display = '';
          return;
        }
        if(noNotesEl) noNotesEl.style.display = 'none';
        items.forEach(it => {
          let href = '#';
          let title = '';
          if(it.href){ href = it.href; }
          else if(it.path){ href = it.path; }
          else if(it.slug){ try{ href = decodeURIComponent(it.slug); }catch(e){ href = it.slug } }
          title = it.title || it.name || it["rel"] || it["path"] || it["href"] || '';
          const li = document.createElement('li');
          const a = document.createElement('a');
          a.href = href;
          a.textContent = title;
          li.appendChild(a);
          if(it.mtime){
            const s = document.createElement('small');
            const d = new Date(it.mtime * 1000);
            s.textContent = `(${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')})`;
            li.appendChild(document.createTextNode(' '));
            li.appendChild(s);
          }
          listEl.appendChild(li);
        });
      }
        
      function fetchJson(url){
        return fetch(url, {cache: 'no-store'}).then(r => { if(!r.ok) throw new Error('not ok'); return r.json(); });
      }
        
      // Attempt modern file
      fetchJson('notes_modern.json').then(render).catch(()=>{
        // fallback to legacy notes.json
        fetchJson('notes.json').then(render).catch(()=>{
          // leave server-side content as-is (or empty message)
        });
      });
    })();
    </script>
        
    </body>
    </html>
    """
    content = content.replace("{PAGE_TITLE}", page_title)
    # Inject server-side generated parts into the HTML template
    content = content.replace("{html_intro}", html_intro)
    content = content.replace("{list_html}", list_html)

    # prepare JSON payload for frontend (modern format)
    # 包含基本字段：href, title (plain text), rel, mtime (秒，或 null)
    json_items = []
    for it in items:
        json_items.append({
            "href": it["href"],
            "title": it.get("display_plain", it.get("display_text", "")),
            "rel": it["rel"],
            "mtime": int(it["mtime"]) if it["mtime"] is not None else None
        })
    json_content = json.dumps(json_items, ensure_ascii=False, indent=2)

    # For backwards compatibility, also produce a legacy-style notes.json array
    # Legacy schema expected by older frontends: { title, path, slug }
    legacy_items = []
    for it in items:
        rel_no_ext = str(Path(it['rel']).with_suffix('')).replace(os.sep, '/')
        if rel_no_ext.endswith('.'):
            rel_no_ext = rel_no_ext[:-1]
        # slug: URL-encoded relative path (basename or full path depending on consumer)
        slug = urllib.parse.quote(rel_no_ext, safe='')
        legacy_items.append({
            "title": it.get("display_plain", it.get("display_text", "")),
            "path": rel_no_ext,
            "slug": slug
        })
    legacy_content = json.dumps(legacy_items, ensure_ascii=False, indent=2)

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
                print(f"备份旧的 {out_path} -> {bak}")
            rotate_backups(out_path, cfg.get("max_backups", 5), verbose=args.verbose)
        except Exception as e:
            print("备份失败：", e)

    # write index.html
    try:
        atomic_write(out_path, content)
    except Exception as e:
        print("写入失败：", e)
        return 2

    # backup notes.json
    if out_json_path.exists() and cfg.get("backup", True):
        ts = time.strftime('%Y%m%d-%H%M%S')
        bakj = out_json_path.with_name(out_json_path.name + ".bak-" + ts)
        try:
            shutil.copy2(out_json_path, bakj)
            if args.verbose:
                print(f"备份旧的 {out_json_path} -> {bakj}")
            rotate_backups(out_json_path, cfg.get("max_backups", 5), verbose=args.verbose)
        except Exception as e:
            if args.verbose:
                print("JSON 备份失败：", e)

    # write legacy-format notes.json (for older frontends)
    try:
        atomic_write(out_json_path, legacy_content)
    except Exception as e:
        print("写入 notes.json 失败（legacy)：", e)
        return 2

    # also write a modern JSON file with richer fields (notes_modern.json)
    modern_json_path = root / (cfg.get('json_output', 'notes.json').rsplit('.', 1)[0] + '_modern.json')
    try:
        # backup modern file if exists
        if modern_json_path.exists() and cfg.get("backup", True):
            ts = time.strftime('%Y%m%d-%H%M%S')
            bakm = modern_json_path.with_name(modern_json_path.name + ".bak-" + ts)
            try:
                shutil.copy2(modern_json_path, bakm)
                if args.verbose:
                    print(f"备份旧的 {modern_json_path} -> {bakm}")
                rotate_backups(modern_json_path, cfg.get("max_backups", 5), verbose=args.verbose)
            except Exception:
                pass
        atomic_write(modern_json_path, json_content)
    except Exception as e:
        if args.verbose:
            print("写入 notes_modern.json 失败：", e)

    print(f"已生成 {out_path}，列出 {len(items)} 个公开笔记（排除 {excluded_privacy} 个私密笔记）。")
    print(f"已生成 {out_json_path}（legacy 格式），并尝试写入 {modern_json_path}（modern 格式）。")
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
