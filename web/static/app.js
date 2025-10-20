// web/static/app.js
async function fetchData() {
  try {
    const r = await fetch("/data", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    document.getElementById("lat").textContent = j.lat ?? "—";
    document.getElementById("lon").textContent = j.lon ?? "—";
    document.getElementById("speed").textContent = j.speed ?? "—";
    document.getElementById("devtime").textContent = j.timestamp ?? "—";
    const d = j.server_ts ? new Date(j.server_ts * 1000).toLocaleString() : "—";
    document.getElementById("svr").textContent = d;
    document.getElementById("status").textContent = "OK";
  } catch (e) {
    document.getElementById("status").textContent = "Error: " + e.message;
  }
}

fetchData();
setInterval(fetchData, 2000);