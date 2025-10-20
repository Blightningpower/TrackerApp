# scripts/inspect_tcp_log.py
from pathlib import Path
import re, binascii

log = Path("scripts/tcp_log.txt")
if not log.exists():
    print("tcp_log.txt niet gevonden.")
    raise SystemExit(1)

raw = log.read_text(encoding="utf-8", errors="replace")
# zoek alles wat tussen aanhalingstekens in jouw log stond (raw from ...: '...') 
# of simpelweg lines met "raw from" en de inhoud extraheren
lines = [l for l in raw.splitlines() if "raw from" in l]
for i,l in enumerate(lines,1):
    m = re.search(r"raw from [^:]+: (.+)$", l)
    if not m: 
        continue
    txt = m.group(1).strip()
    # als je raw hex bytes hebt als Python repr (b'...') - probeer hexlify
    b = None
    try:
        # probeer hex decode als het byteslike escaped is
        # strip surrounding quotes/backslashes if present
        s = txt.strip("'\"")
        # brute-force: take the literal bytes by encoding as latin-1
        b = s.encode('latin1', errors='replace')
    except Exception:
        b = txt.encode('utf-8', errors='replace')

    print("=== chunk", i, "===")
    print("ASCII extract:", ''.join(ch for ch in b.decode('latin1', errors='replace') if 32 <= ord(ch) <= 126)[:200])
    print("HEX:", binascii.hexlify(b)[:200])
    # zoek gevoelige patterns zoals OPEN_JT808 of N[0-9A-Z]+
    for patt in (b"OPEN_JT808", b"JT808", b"OPEN"):
        if patt in b:
            print("FOUND pattern:", patt.decode())

    # try find decimal coords in ASCII text
    m2 = re.search(r"(-?\d+\.\d+)[,;\s]+(-?\d+\.\d+)", b.decode('latin1', errors='replace'))
    if m2:
        print("Possible coords:", m2.group(1), m2.group(2))
    print()