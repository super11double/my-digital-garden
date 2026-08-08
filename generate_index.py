import os
import glob
import re

def has_chinese(text):
    return re.search('[\u4e00-\u9fff]', text) is not None

md_files = glob.glob('**/*.md', recursive=True)
md_files = [
    f for f in md_files
    if f not in ['generate_index.py', 'README.md']
    and not has_chinese(os.path.basename(f))
]

list_items = ""
for file in sorted(md_files):
    name = os.path.splitext(file)[0].replace(os.sep, '/')
    list_items += f'        <li><a href="{name}">{name}</a></li>\n'

html_content = f'''<!DOCTYPE html>
<html>
<head>
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
