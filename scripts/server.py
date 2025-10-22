# scripts/server.py
import socket, json, time, re, os
from pathlib import Path
import struct
from datetime import datetime

def unescape_jt(data: bytes) -> bytes:
    # JT808 escape: 7D 01 -> 7D, 7D 02 -> 7E
    return data.replace(b'\x7d\x01', b'\x7d').replace(b'\x7d\x02', b'\x7e')

def xor_checksum_ok(frame_no_delims: bytes) -> bool:
    # frame_no_delims includes everything except leading/trailing 0x7e and includes checksum as last byte
    if len(frame_no_delims) < 2:
        return False
    body = frame_no_delims[:-1]
    chksum = frame_no_delims[-1]
    cs = 0
    for b in body:
        cs ^= b
    return cs == chksum

def bcd6_to_timestr(b: bytes) -> str:
    # 6 bytes BCD -> 'YYYY-MM-DD HH:MM:SS' (spec has YYMMDDhhmmss)
    # many JT808 timestamps are YYMMDDhhmmss -> assume 20YY
    if len(b) != 6:
        return ""
    y = 2000 + int(f"{b[0]:02x}")  # careful: b[i] are bytes, but converting to hex gives e.g. 0x20 -> '20'
    # safer to convert each nibble decimal via format:
    digits = []
    for byte in b:
        digits.append(f"{byte:02x}")
    # digits = ['yy','mm','dd','hh','mm','ss']
    try:
        yy = int(digits[0])
        mm = int(digits[1])
        dd = int(digits[2])
        hh = int(digits[3])
        mi = int(digits[4])
        ss = int(digits[5])
        return f"{2000+yy:04d}-{mm:02d}-{dd:02d} {hh:02d}:{mi:02d}:{ss:02d}"
    except Exception:
        return ""

def parse_jt808(raw_bytes: bytes):
    """
    Try to parse JT808 frames in raw_bytes.
    Returns a dict with lat/lon/speed/timestamp if a 0x0200 location is found,
    or None if not parsed.
    """
    results = []
    # split on 0x7e (frame delimiter). keep bytes between delimiters
    parts = raw_bytes.split(b'\x7e')
    for p in parts:
        if not p:
            continue
        # p may contain the frame bytes including checksum
        unescaped = unescape_jt(p)
        # require at least header+checksum
        if len(unescaped) < 5:
            continue
        if not xor_checksum_ok(unescaped):
            # optionally skip or still try
            continue
        # payload without checksum:
        payload = unescaped[:-1]
        if len(payload) < 12:
            continue
        # header parsing
        msg_id = int.from_bytes(payload[0:2], 'big')
        msg_props = int.from_bytes(payload[2:4], 'big')
        body_len = msg_props & 0x03FF  # low 10 bits
        # header length normally: 2(msgid)+2(props)+6(terminal)+2(serial) = 12
        header_len = 12
        if len(payload) < header_len + body_len:
            continue
        body = payload[header_len:header_len+body_len]
        # 0x0200 is location report
        if msg_id == 0x0200:
            # body layout (standard): alarm(4), status(4), lat(4), lon(4),
            # altitude(2), speed(2), direction(2), time(6)
            if len(body) < 4+4+4+4+2+2+2+6:
                continue
            alarm = int.from_bytes(body[0:4], 'big')
            status = int.from_bytes(body[4:8], 'big')
            lat_raw = int.from_bytes(body[8:12], 'big', signed=False)
            lon_raw = int.from_bytes(body[12:16], 'big', signed=False)
            alt = int.from_bytes(body[16:18], 'big')
            speed_raw = int.from_bytes(body[18:20], 'big')
            direction = int.from_bytes(body[20:22], 'big')
            time_bcd = body[22:28]
            # convert lat/lon: spec stores degrees * 1e6
            lat = lat_raw / 1e6
            lon = lon_raw / 1e6
            # speed unit: device dependent (often 1/10 km/h or km/h) -> leave raw for now
            # timestamp from device:
            devtime = bcd6_to_timestr(time_bcd)
            results.append({
                "protocol": "jt808",
                "msg_id": hex(msg_id),
                "alarm": alarm,
                "status": status,
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "speed_raw": speed_raw,
                "direction": direction,
                "timestamp": devtime
            })
    # return first found (or list if you prefer)
    return results[0] if results else None

HOST = "0.0.0.0"
PORT = 8010
LOG = Path(__file__).parent / "tcp_log.txt"
DATA_FILE = Path(__file__).parent.parent / "web" / "data.json"
FLASK_FORWARD = os.environ.get("FLASK_FORWARD")  # e.g. "http://127.0.0.1:8080/update"
TRACKER_SECRET = os.environ.get("TRACKER_SECRET")

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    LINE = f"[{ts}] {msg}\n"
    print(LINE, end="")
    try:
        LOG.write_text(LOG.read_text(encoding="utf-8") + LINE if LOG.exists() else LINE, encoding="utf-8")
    except Exception:
        pass

def write_data(d):
    try:
        DATA_FILE.write_text(json.dumps(d), encoding="utf-8")
    except Exception as e:
        log(f"write error: {e}")

def try_parse_coords(txt):
    m = re.search(r"(-?\d+\.\d+)[,;\s]+(-?\d+\.\d+)", txt)
    if m:
        return {"lat": float(m.group(1)), "lon": float(m.group(2))}
    return None

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen(5)
    log(f"TCP server listening on {HOST}:{PORT}")
    while True:
        conn, addr = s.accept()
        with conn:
            client = f"{addr[0]}:{addr[1]}"
            log(f"connected: {client}")
            conn.settimeout(5.0)
            chunks = []
            try:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    chunks.append(data)
            except socket.timeout:
                pass
            raw = b"".join(chunks)
            try:
                txt = raw.decode('utf-8', errors='replace').strip()
            except Exception:
                txt = str(raw)
            log(f"raw from {client}: {txt[:1000]!r}")

            parsed = None
            try:
                parsed = json.loads(txt)
                log(f"parsed JSON from {client}: {parsed}")
            except Exception:
                coords = try_parse_coords(txt)
                if coords:
                    parsed = coords
                    log(f"parsed coords from {client}: {parsed}")
                else:
                    log("no JSON/coords parsed")

            if isinstance(parsed, dict):
                write_data(parsed)
                log("wrote to data.json")

                if FLASK_FORWARD:
                    try:
                        import requests
                        headers = {"Content-Type":"application/json"}
                        if TRACKER_SECRET:
                            headers["X-Tracker-Secret"] = TRACKER_SECRET
                        r = requests.post(FLASK_FORWARD, json=parsed, headers=headers, timeout=5)
                        log(f"forwarded to {FLASK_FORWARD}: {r.status_code}")
                    except Exception as e:
                        log(f"forward failed: {e}")

            log(f"connection closed: {client}")