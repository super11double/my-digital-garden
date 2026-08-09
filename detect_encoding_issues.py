from pathlib import Path
root = Path('.').resolve()
candidates = list(root.glob('notes/*')) + [root/'notes.json', root/'notes_modern.json', root/'index.html']
problems = []
for p in candidates:
    if not p.exists():
        continue
    b = p.read_bytes()
    try:
        _ = b.decode('utf-8')
    except Exception as e:
        problems.append((str(p), repr(e)))

print('Problems found:')
for p, e in problems:
    print(p, '-', e)
if not problems:
    print(' (none)')
