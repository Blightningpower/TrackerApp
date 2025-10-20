# web/app.py
from flask import Flask, jsonify, request, render_template
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
import json, time, os

APP = Flask(__name__)
DATA_FILE = Path(__file__).parent / "data.json"

def read_data():
    if not DATA_FILE.exists():
        return {}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_data(d):
    DATA_FILE.write_text(json.dumps(d), encoding="utf-8")

@APP.route("/")
def index():
    return render_template("index.html")

@APP.route("/data", methods=["GET"])
def get_data():
    d = read_data()
    d.setdefault("server_ts", int(time.time()))
    return jsonify(d)

TRACKER_SECRET = os.environ.get("TRACKER_SECRET")
if not TRACKER_SECRET:
    raise RuntimeError("TRACKER_SECRET missing — set environment variable or create .env with TRACKER_SECRET")

@APP.route("/update", methods=["POST"])
def update():
    # prefer header but accept body secret too
    header_secret = request.headers.get("X-Tracker-Secret")
    try:
        j = request.get_json(force=True)
    except Exception:
        return {"error": "invalid json"}, 400

    body_secret = None
    if isinstance(j, dict):
        body_secret = j.get("secret")
    ok = (header_secret == TRACKER_SECRET) or (body_secret == TRACKER_SECRET)

    if not ok:
        return {"error": "forbidden"}, 403

    # remove secret if present before saving
    if isinstance(j, dict) and "secret" in j:
        del j["secret"]

    # validate minimal fields
    if not isinstance(j, dict) or "lat" not in j or "lon" not in j:
        return {"error": "missing lat/lon"}, 400

    write_data(j)
    return {"status": "ok"}, 200

if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=8080, debug=True)