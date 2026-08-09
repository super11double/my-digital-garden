#!/usr/bin/env python3
"""Generate simple HTML pages from notes/*.md and convert [[Wiki]] links.
Writes each note to notes/{basename}/index.html so links like notes/name work.

注意：本脚本已由仓库根目录的 generate_index.py 取代（后者会在 CI 中同步生成
笔记页并转换 [[Wiki]] 链接）。这里保留为独立工具，Wiki 链接使用基于 SITE_BASE
的绝对地址，避免从 notes/<name>/ 子目录打开时相对链接解析成 404。
"""
from pathlib import Path
import re
import os
import unicodedata
import urllib.parse
import sys

ROOT = Path('.').resolve()
NOTES_DIR = ROOT / 'notes'
OUT_DIR = NOTES_DIR  # we'll write notes/<basename>/index.html
SITE_BASE = os.environ.get('SITE_BASE', 'https://super11double.github.io/my-digital-garden/')
WIKI_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

# read all markdown files
md_files = sorted([p for p in NOTES_DIR.glob('*.md') if p.is_file()])
# build alias map: rel_no_ext -> href (absolute URL, safe from 404)
alias_map = {}
basename_counts = {}
for p in md_files:
    b = p.stem
    basename_counts[b] = basename_counts.get(b, 0) + 1
for p in md_files:
    # compute path relative to notes/ directory (preserves subdirs)
    rel_no_ext = str(p.relative_to(NOTES_DIR).with_suffix('')).replace('\\','/')
    basename = p.stem
    # use directory-style href ending with '/', prefixed with SITE_BASE (absolute)
    href = SITE_BASE.rstrip('/') + '/' + 'notes/' + urllib.parse.quote(rel_no_ext, safe='/') + '/'
    # write to notes/<rel_no_ext>/index.html so href 'notes/<rel_no_ext>/' works
    alias_map[rel_no_ext] = href
    alias_map[rel_no_ext.lower()] = href
    # add basename keys only when unique
    if basename_counts.get(basename,0) == 1:
        alias_map[basename] = href
        alias_map[basename.lower()] = href


def convert_wiki(text):
    if not text:
        return text
    def repl(m):
        target = m.group(1).strip()
        label = m.group(2)
        label = label.strip() if label else None
        key = target
        href = alias_map.get(key) or alias_map.get(key.lower())
        if not href:
            return m.group(0)  # leave as-is
        display = label if label else target
        return f'<a href="{html_escape(href)}">{html_escape(display)}</a>'
    return WIKI_RE.sub(repl, text)


def html_escape(s):
    return (s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
            .replace('"','&quot;').replace("'","&#39;"))

# use markdown if available
try:
    import markdown
    has_md = True
except Exception:
    has_md = False

for p in md_files:
    text = p.read_text(encoding='utf-8')
    # strip frontmatter
    content = text
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            content = parts[2]
    # convert markdown to html if possible
    if has_md:
        html_body = markdown.markdown(content, extensions=['extra','sane_lists'])
        # convert wiki links in the resulting HTML (replace [[...]] with anchors)
        html_body = convert_wiki(html_body)
    else:
        # very simple fallback: escape plain text then convert wiki links so anchors are not double-escaped
        parts = []
        for line in content.splitlines():
            if not line.strip():
                continue
            escaped = html_escape(line)
            processed = convert_wiki(escaped)
            parts.append(f'<p>{processed}</p>')
        html_body = '\n'.join(parts)
    title = p.stem
    page = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html_escape(title)}</title>
<style>body{{font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; padding:1rem;}}</style>
</head>
<body>
<a href="{html_escape(SITE_BASE)}">← Home</a>
<article>
{html_body}
</article>
</body>
</html>"""
    out_dir = OUT_DIR / p.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'index.html'
    out_path.write_text(page, encoding='utf-8')
    print('Wrote', out_path)

print('Done')
