from flask import Flask, jsonify, request, render_template, abort
from pathlib import Path
from datetime import datetime, timezone
import json, os

APP = Flask(__name__)

# app.py staat in web/, dus data.json ligt naast app.py in web/
DATA_FILE = Path(__file__).parent / "data.json"

# ===== helpers =====
def _now_local_str() -> str:
    """Lokale timestamp voor weergave (YYYY-MM-DD HH:MM:SS)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _now_utc_iso() -> str:
    """ISO8601 UTC voor machines (2025-10-22T13:37:00+00:00)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def read_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def write_data(obj: dict):
    obj = dict(obj)
    obj["server_ts"] = _now_local_str()   # voor mensen
    obj["server_ts_iso"] = _now_utc_iso() # voor machines
    DATA_FILE.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

# ===== routes =====
@APP.route("/")
def index():
    return render_template("index.html")

@APP.route("/data")
def data():
    return jsonify(read_data())

@APP.route("/update", methods=["POST", "GET"])
def update():
    # Optioneel: simpele beveiliging met secret header
    expected = os.getenv("TRACKER_SECRET")
    if expected and request.headers.get("X-Tracker-Secret") != expected:
        abort(401)

    # Accepteer JSON, form-encoded of querystring
    j = {}
    if request.method == "POST":
        if request.is_json:
            j = request.get_json(silent=True) or {}
        else:
            j = request.form.to_dict(flat=True)
    else:
        j = request.args.to_dict(flat=True)

    # Variaties op sleutel-namen
    lat = j.get("lat") or j.get("latitude")
    lon = j.get("lon") or j.get("lng") or j.get("longitude")
    spd_kmh = j.get("speed_kmh")
    spd_mps = j.get("speed") or j.get("spd")  # m/s

    if lat is None or lon is None:
        return jsonify({"error": "lat/lon required"}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return jsonify({"error": "invalid lat/lon"}), 400

    speed_kmh = None
    if spd_kmh not in (None, ""):
        try:
            speed_kmh = float(spd_kmh)
        except Exception:
            speed_kmh = None
    elif spd_mps not in (None, ""):
        try:
            speed_kmh = float(spd_mps) * 3.6
        except Exception:
            speed_kmh = None

    out = {
        "lat": lat,
        "lon": lon,
        "speed_kmh": round(speed_kmh, 1) if isinstance(speed_kmh, float) else None,
        "ts_client": j.get("timestamp") or j.get("time") or None,
        "source": request.remote_addr,
    }
    write_data(out)
    return jsonify({"status": "ok", "saved": out})

if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=8080, debug=True)