#!/usr/bin/env python3
"""Strip UTF-8 BOM from generated files if present.
Used by .github/workflows/update-index.yml
"""
from pathlib import Path
files = ['index.html', 'notes.json', 'notes_modern.json']
for f in files:
    p = Path(f)
    if not p.exists():
        continue
    b = p.read_bytes()
    if b.startswith(b'\xef\xbb\xbf'):
        p.write_bytes(b[3:])
        print('Stripped BOM from', f)
