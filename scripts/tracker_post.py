# scripts/tracker_post.py
import time, random, os, requests

SERVER = os.environ.get("TRACKER_ENDPOINT", "http://127.0.0.1:8080/update")
TRACKER_SECRET = os.environ.get("TRACKER_SECRET")

def send(payload):
    headers = {"Content-Type":"application/json"}
    if TRACKER_SECRET:
        headers["X-Tracker-Secret"] = TRACKER_SECRET
    r = requests.post(SERVER, json=payload, headers=headers, timeout=5)
    print("sent:", payload, "->", r.status_code)

if __name__ == "__main__":
    while True:
        payload = {
            "lat": 51.4416 + random.uniform(-0.002, 0.002),
            "lon": 5.4697 + random.uniform(-0.002, 0.002),
            "speed": random.randint(0,8),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            send(payload)
        except Exception as e:
            print("error:", e)
        time.sleep(5)