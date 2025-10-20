# scripts/server.py
"""
TCP trapserver voor jouw tracker:
- luistert op HOST:PORT
- slaat geparste locatie (lat/lon/speed/timestamp) op in ../web/data.json
- optioneel forward naar FLASK_FORWARD (env) met X-Tracker-Secret header (TRACKER_SECRET env)
- logt gebeurtenissen naar scripts/tcp_log.txt
Geschikt als basis; ondersteunt standaard JT808 0x0200 location parsing (niet alle vendor-varianten).
"""
from pathlib import Path
import socket
import json
import time
import re
import os
import struct
from typing import Optional, Dict, Any, List

HOST = "0.0.0.0"
PORT = 8010

BASE = Path(__file__).parent
LOG = BASE / "tcp_log.txt"
DATA_FILE = BASE.parent / "web" / "data.json"  # ../web/data.json
FLASK_FORWARD = os.environ.get("FLASK_FORWARD")  # voorbeeld: "http://127.0.0.1:8080/update"
TRACKER_SECRET = os.environ.get("TRACKER_SECRET")  # optioneel, gebruikt bij forward

# --- utilities -------------------------------------------------------------

def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        txt = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
        LOG.write_text(txt + line + "\n", encoding="utf-8")
    except Exception:
        # laat falen geen crash veroorzaken
        pass

def safe_write_json(path: Path, obj: Dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        log(f"write error: {e}")
        return False

# --- JT808 parsing helpers -------------------------------------------------

def unescape_jt(b: bytes) -> bytes:
    # JT808 escape rules: 0x7d 0x01 -> 0x7d, 0x7d 0x02 -> 0x7e
    # apply sequential replace
    return b.replace(b'\x7d\x01', b'\x7d').replace(b'\x7d\x02', b'\x7e')

def xor_checksum_ok(frame_no_delims: bytes) -> bool:
    # frame_no_delims: bytes between delimiters, last byte is checksum
    if len(frame_no_delims) < 2:
        return False
    body = frame_no_delims[:-1]
    chksum = frame_no_delims[-1]
    cs = 0
    for b in body:
        cs ^= b
    return cs == chksum

def bcd6_to_timestr(b: bytes) -> str:
    # 6 BCD bytes in JT808 are YY MM DD hh mm ss (each byte = two BCD digits)
    if len(b) != 6:
        return ""
    digits = []
    for byte in b:
        hi = (byte >> 4) & 0xF
        lo = byte & 0xF
        digits.append(str(hi))
        digits.append(str(lo))
    try:
        yy = int(digits[0] + digits[1])
        mm = int(digits[2] + digits[3])
        dd = int(digits[4] + digits[5])
        hh = int(digits[6] + digits[7])
        mi = int(digits[8] + digits[9])
        ss = int(digits[10] + digits[11])
        year = 2000 + yy
        return f"{year:04d}-{mm:02d}-{dd:02d} {hh:02d}:{mi:02d}:{ss:02d}"
    except Exception:
        return ""

def parse_jt808(raw_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse JT808 frames in raw_bytes and return first found location dict or None.
    Supports:
      - frame delimiters 0x7E
      - escaping 0x7D 0x01 / 0x7D 0x02
      - checksum verify (XOR)
      - 0x0200 location message parsing (alarm,status,lat,lon,alt,speed,dir,time)
    Returns dict like: {protocol:"jt808", lat:..., lon:..., speed:..., timestamp:..., raw: ...}
    """
    parts = raw_bytes.split(b'\x7e')
    for p in parts:
        if not p:
            continue
        unescaped = unescape_jt(p)
        # need at least msg header + checksum
        if len(unescaped) < 5:
            continue
        # verify checksum
        if not xor_checksum_ok(unescaped):
            # skip invalid frames
            continue
        payload_with_checksum = unescaped
        payload = payload_with_checksum[:-1]  # without checksum
        if len(payload) < 12:
            continue
        # parse header
        msg_id = int.from_bytes(payload[0:2], 'big')
        msg_props = int.from_bytes(payload[2:4], 'big')
        # body length (low 10 bits)
        body_len = msg_props & 0x03FF
        # check subpackage flag (bit 13) -> if set, there's extra 4 bytes in header for package info
        subpackage_flag = bool(msg_props & 0x2000)
        # header base length: msgid(2)+props(2)+terminal(6)+serial(2) = 12
        header_len = 12
        if subpackage_flag:
            header_len += 4  # package info: total packages + package seq
        if len(payload) < header_len + body_len:
            # frame incomplete (shouldn't happen if checksum ok) -> skip
            continue
        body = payload[header_len:header_len + body_len]
        # handle location message
        if msg_id == 0x0200:
            # expect at least 4+4+4+4+2+2+2+6 = 28 bytes
            if len(body) < 28:
                continue
            alarm = int.from_bytes(body[0:4], 'big')
            status = int.from_bytes(body[4:8], 'big')
            lat_raw = int.from_bytes(body[8:12], 'big', signed=False)
            lon_raw = int.from_bytes(body[12:16], 'big', signed=False)
            alt = int.from_bytes(body[16:18], 'big', signed=False)
            speed_raw = int.from_bytes(body[18:20], 'big', signed=False)
            direction = int.from_bytes(body[20:22], 'big', signed=False)
            time_bcd = body[22:28]
            lat = lat_raw / 1e6
            lon = lon_raw / 1e6
            # commonly speed is in 1/10 km/h, convert to km/h as heuristic
            speed_kmh = round(speed_raw / 10.0, 1)
            devtime = bcd6_to_timestr(time_bcd)
            return {
                "protocol": "jt808",
                "msg_id": hex(msg_id),
                "alarm": alarm,
                "status": status,
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "speed_raw": speed_raw,
                "speed_kmh": speed_kmh,
                "direction": direction,
                "timestamp": devtime,
                "raw_preview": raw_bytes[:200].hex()
            }
    return None

# --- fallback simple ASCII coords parser ----------------------------------

def try_parse_coords_ascii(txt: str) -> Optional[Dict[str, Any]]:
    """
    Probeer eenvoudige ASCII "lat lon" of "lat,lon" of JSON in tekst te parsen.
    Retourneert dict of None.
    """
    # JSON first
    try:
        j = json.loads(txt)
        if isinstance(j, dict) and "lat" in j and "lon" in j:
            return j
    except Exception:
        pass
    # zoek decimal coords
    m = re.search(r"(-?\d+\.\d+)[,;\s]+(-?\d+\.\d+)", txt)
    if m:
        try:
            return {"lat": float(m.group(1)), "lon": float(m.group(2))}
        except Exception:
            return None
    return None

# --- main server loop -----------------------------------------------------

def forward_to_flask(parsed: Dict[str, Any]) -> None:
    if not FLASK_FORWARD:
        return
    try:
        import requests
        headers = {"Content-Type": "application/json"}
        if TRACKER_SECRET:
            headers["X-Tracker-Secret"] = TRACKER_SECRET
        r = requests.post(FLASK_FORWARD, json=parsed, headers=headers, timeout=5)
        log(f"forwarded to {FLASK_FORWARD}: {r.status_code}")
    except Exception as e:
        log(f"forward failed: {e}")

def write_found(parsed: Dict[str, Any]) -> None:
    # voeg server timestamp toe
    parsed_copy = dict(parsed)
    parsed_copy["server_ts"] = int(time.time())
    safe_write_json(DATA_FILE, parsed_copy)
    log(f"wrote to {DATA_FILE} -> {json.dumps(parsed_copy, ensure_ascii=False)[:400]}")

def run_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)
        log(f"TCP server listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            with conn:
                client = f"{addr[0]}:{addr[1]}"
                log(f"connected: {client}")
                conn.settimeout(5.0)
                chunks: List[bytes] = []
                try:
                    while True:
                        data = conn.recv(4096)
                        if not data:
                            break
                        chunks.append(data)
                except socket.timeout:
                    # client stopte met sturen
                    pass
                raw = b"".join(chunks)
                try:
                    txt = raw.decode('utf-8', errors='replace').strip()
                except Exception:
                    txt = ""
                preview = raw[:1000] if len(raw) > 0 else txt
                log(f"raw from {client}: {preview!r}")

                parsed = None
                # 1) probeer ASCII/JSON parse
                if txt:
                    parsed = try_parse_coords_ascii(txt)

                # 2) als nog niks, probeer JT808 binaire parse op raw bytes
                if parsed is None and raw:
                    try:
                        jt = parse_jt808(raw)
                        if jt:
                            parsed = jt
                    except Exception as e:
                        log(f"jt parse error: {e}")

                if isinstance(parsed, dict):
                    try:
                        write_found(parsed)
                    except Exception as e:
                        log(f"write_found error: {e}")
                    # optional forward
                    if FLASK_FORWARD:
                        try:
                            forward_to_flask(parsed)
                        except Exception as e:
                            log(f"forward exception: {e}")
                else:
                    log("no JSON/coords parsed")

                log(f"connection closed: {client}")

if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        log("shutting down (KeyboardInterrupt)")
    except Exception as exc:
        log(f"fatal server error: {exc}")