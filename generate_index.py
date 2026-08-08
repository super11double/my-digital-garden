import os
import glob
import urllib.parse

IGNORE_BASENAMES = {'generate_index.py', 'README.md'}
IGNORE_DIRS = {'.git', 'node_modules', '.venv', 'venv', '.obsidian'}

md_files = [
    f for f in glob.glob('**/*.md', recursive=True)
    if os.path.basename(f) not in IGNORE_BASENAMES
    and not any(part in IGNORE_DIRS for part in f.split(os.sep))
]

list_items = ""
for file in sorted(md_files):
    path_no_ext = os.path.splitext(file)[0].replace(os.sep, '/')
    href = urllib.parse.quote(path_no_ext + '.md', safe='/')
    display = os.path.splitext(os.path.basename(file))[0]
    list_items += f'        <li><a href="{href}">{display}</a></li>\\n'

html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>我的知识库</title>
</head>
<body>
    <h1>我的知识库</h1>
    <ul>
{list_items}    </ul>
</body>
</html>
'''

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"✅ Index generated with {len(md_files)} files.")
