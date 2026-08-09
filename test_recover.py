from pathlib import Path
p = Path('notes/爱情.md')
b = p.read_bytes()
print('raw bytes head:', b[:120])
try:
    t_utf8 = b.decode('utf-8')
    print('\n--- decoded utf-8 head ---\n', t_utf8[:400])
except Exception as e:
    print('utf8 decode failed', e)
# attempt recovery: assume double-encoded
try:
    recovered = t_utf8.encode('latin-1').decode('utf-8')
    print('\n--- recovered (latin1->utf8) head ---\n', recovered[:400])
except Exception as e:
    print('recovery latin1->utf8 failed', e)
# also try decode as cp936
try:
    t_cp936 = b.decode('cp936')
    print('\n--- decoded cp936 head ---\n', t_cp936[:400])
except Exception as e:
    print('cp936 decode failed', e)
