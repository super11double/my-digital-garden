import os
import glob
import re

# 检查文件名是否包含中文
def has_chinese(text):
    return re.search('[\u4e00-\u9fff]', text) is not None

# 扫描所有 .md 文件（包括子文件夹）
md_files = glob.glob('**/*.md', recursive=True)

# 排除掉脚本本身和 README，以及文件名含中文的文件
md_files = [
    f for f in md_files
    if f not in ['generate_index.py', 'README.md']
    and not has_chinese(os.path.basename(f))
]

# 生成 HTML 列表
list_items = ""
for file in sorted(md_files):
    name = os.path.splitext(file)[0].replace(os.sep, '/')  # 保留路径，用 / 分隔
    # 如果文件在子文件夹里，链接路径要包含文件夹
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
