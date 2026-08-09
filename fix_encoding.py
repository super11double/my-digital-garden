import sys, pathlib
root = pathlib.Path('.').resolve()
candidates = list(root.glob('notes/*.md')) + [root/'notes.json', root/'notes_modern.json', root/'index.html']
fixed = []
for p in candidates:
    if not p.exists():
        continue
    try:
        b = p.read_bytes()
    except Exception as e:
        print(f"[ERR] reading {p}: {e}", file=sys.stderr)
        continue
    orig = b
    changed = False
    # Remove UTF-8 BOM
    if b.startswith(b'\xef\xbb\xbf'):
        b = b[3:]
        changed = True
    text = None
    try:
        text = b.decode('utf-8')
    except UnicodeDecodeError:
        # try GBK (common on Windows/Chinese content)
        try:
            text = b.decode('cp936')
            changed = True
        except Exception:
            try:
                text = b.decode('latin-1')
                changed = True
            except Exception:
                print(f"[SKIP] Cannot decode {p}", file=sys.stderr)
                continue
    # If text is same when encoded to utf-8 and orig equals, skip
    if not changed and orig == text.encode('utf-8'):
        continue
    # write normalized utf-8 without BOM
    try:
        p.write_text(text, encoding='utf-8')
        fixed.append(str(p))
    except Exception as e:
        print(f"[ERR] writing {p}: {e}", file=sys.stderr)

print('Fixed files:')
if fixed:
    for f in fixed:
        print(' -', f)
else:
    print(' (none)')
