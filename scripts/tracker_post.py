# scripts/tracker_post.py
import time, requests, random, os

SERVER = "http://127.0.0.1:8080/update"
TRACKER_SECRET = os.environ.get("TRACKER_SECRET")
if not TRACKER_SECRET:
    raise RuntimeError("TRACKER_SECRET missing — set env var or create .env")

def send(payload):
    headers = {"Content-Type": "application/json", "X-Tracker-Secret": TRACKER_SECRET}
    try:
        r = requests.post(SERVER, json=payload, headers=headers, timeout=5)
        r.raise_for_status()
        print("sent:", payload)
    except Exception as e:
        print("error sending:", e)

if __name__ == "__main__":
    while True:
        payload = {
            "lat": 51.4416 + random.uniform(-0.001, 0.001),
            "lon": 5.4697 + random.uniform(-0.001, 0.001),
            "speed": random.randint(0,4),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        send(payload)
        time.sleep(5)