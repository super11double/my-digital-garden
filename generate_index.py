import os
import glob

# 扫描所有 .md 文件（排除脚本本身和 README）
md_files = glob.glob('*.md')
md_files = [f for f in md_files if f not in ['generate_index.py', 'README.md']]

# 生成 HTML 列表
list_items = ""
for file in sorted(md_files):
    name = os.path.splitext(file)[0]
    list_items += f'        <li><a href="{name}">{name}</a></li>\n'

# 写入 index.html
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
