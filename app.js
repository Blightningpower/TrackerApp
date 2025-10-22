// === Kaart instellen ===
const DEFAULT_CENTER = [51.4416, 5.4697];
const map = L.map("map").setView(DEFAULT_CENTER, 16);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const trackerMarker = L.marker(DEFAULT_CENTER).addTo(map);
let meMarker = null, meAccuracy = null;
let linkLine = null;          // lijn tussen myPos en trackerPos
let didFitOnce = false;       // éénmalig fitBounds wanneer beide posities bekend zijn

// UI refs
const elLat = document.getElementById("lat");
const elLon = document.getElementById("lon");
const elSpeed = document.getElementById("speed");
const elSvr = document.getElementById("svr");
const elStatus = document.getElementById("status");
const btn = document.getElementById("startUpload");
const follow = document.getElementById("follow");
const uploadStatus = document.getElementById("uploadStatus");

// Plaats voor afstandstekst (maken als die niet bestaat)
let distEl = document.getElementById("dist");
if (!distEl) {
  const meta = document.querySelector(".meta");
  distEl = document.createElement("div");
  distEl.innerHTML = "<b>Afstand tot tracker:</b> <span id='distVal'>—</span>";
  meta && meta.appendChild(distEl);
}
const elDistVal = document.getElementById("distVal") || distEl.querySelector("#distVal");

// Navigatie
let myPos = null, trackerPos = null;
const modeSel = document.getElementById("mode");
const btnG = document.getElementById("btnGmaps");
const btnA = document.getElementById("btnApple");
const btnW = document.getElementById("btnWaze");
const btnO = document.getElementById("btnOSM");
const navHint = document.getElementById("navHint");

function enableNavButtons(enable, msg) {
  [btnG, btnA, btnW, btnO].forEach((a) => {
    a.style.pointerEvents = enable ? "" : "none";
    a.style.opacity = enable ? "" : "0.5";
  });
  navHint.textContent = msg || (enable ? "Klaar om te navigeren." : "Wachten op locaties…");
}
enableNavButtons(false);

function urlEncodeLatLon(p) {
  return `${p[0].toFixed(6)},${p[1].toFixed(6)}`;
}

function updateNavLinks() {
  if (!myPos || !trackerPos) {
    enableNavButtons(false);
    return;
  }
  const mode = modeSel?.value || "driving";
  const o = urlEncodeLatLon(myPos), d = urlEncodeLatLon(trackerPos);

  // Google Maps
  const g = new URL("https://www.google.com/maps/dir/");
  g.searchParams.set("api", "1");
  g.searchParams.set("origin", o);
  g.searchParams.set("destination", d);
  g.searchParams.set("travelmode", mode);
  btnG.href = g;

  // Apple Kaarten
  const dirMap = { driving: "d", walking: "w", bicycling: "r", transit: "d" };
  const a = new URL("https://maps.apple.com/");
  a.searchParams.set("saddr", o);
  a.searchParams.set("daddr", d);
  a.searchParams.set("dirflg", dirMap[mode] || "d");
  btnA.href = a;

  // Waze
  const w = new URL("https://waze.com/ul");
  w.searchParams.set("ll", d);
  w.searchParams.set("navigate", "yes");
  w.searchParams.set("zoom", "17");
  btnW.href = w;

  // OpenStreetMap
  const eng = mode === "walking" ? "foot" : mode === "bicycling" ? "bicycle" : "car";
  const [olat, olon] = o.split(","), [dlat, dlon] = d.split(",");
  btnO.href = `https://www.openstreetmap.org/directions?engine=fossgis_osrm_${eng}&route=${olat},${olon};${dlat},${dlon}`;

  enableNavButtons(true);
}
modeSel.addEventListener("change", updateNavLinks);

// --- Afstand & lijn & viewport ---
function haversineMeters(a, b) {
  // a=[lat,lon], b=[lat,lon]
  const R = 6371000; // m
  const toRad = (x) => x * Math.PI / 180;
  const dLat = toRad(b[0] - a[0]);
  const dLon = toRad(b[1] - a[1]);
  const la1 = toRad(a[0]), la2 = toRad(b[0]);
  const h = Math.sin(dLat/2)**2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon/2)**2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function updateDistanceAndView() {
  if (!myPos || !trackerPos) {
    elDistVal && (elDistVal.textContent = "—");
    return;
  }

  // Afstand tonen
  const d = haversineMeters(myPos, trackerPos);
  elDistVal.textContent = d >= 1000 ? (d/1000).toFixed(2) + " km" : Math.round(d) + " m";

  // Lijn tekenen
  if (!linkLine) {
    linkLine = L.polyline([myPos, trackerPos], { dashArray: "6,8" }).addTo(map);
  } else {
    linkLine.setLatLngs([myPos, trackerPos]);
  }

  // Viewport: als follow UIT staat, eenmaal fitten zodat beide in beeld zijn
  if (!follow.checked && !didFitOnce) {
    const bounds = L.latLngBounds([myPos, trackerPos]).pad(0.2);
    map.fitBounds(bounds, { animate: false });
    didFitOnce = true;
  }
}

// === Data ophalen van PHP ===
async function fetchData() {
  try {
    const r = await fetch("data.json?nocache=" + Date.now(), { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();

    const lat = Number(j.lat), lon = Number(j.lon);
    const ok = Number.isFinite(lat) && Number.isFinite(lon);
    const speed_kmh = j.speed_kmh != null ? Number(j.speed_kmh) : null;

    elSvr.textContent = j.server_ts || "—";
    elStatus.textContent = ok ? "OK" : "Wachten op data";

    if (ok) {
      elLat.textContent = lat.toFixed(6);
      elLon.textContent = lon.toFixed(6);
      elSpeed.textContent = (speed_kmh != null && isFinite(speed_kmh))
        ? speed_kmh.toFixed(1) + " km/h" : "—";

      trackerMarker.setLatLng([lat, lon])
                   .bindPopup(`Lat: ${lat.toFixed(6)}<br>Lon: ${lon.toFixed(6)}`);

      trackerPos = [lat, lon];
      updateNavLinks();
      updateDistanceAndView();

      if (follow.checked) {
        // volgen = focus op tracker, maar afstandslijn blijft gewoon
        map.setView([lat, lon], Math.max(map.getZoom(), 16), { animate: false });
        didFitOnce = false; // als je weer uit follow gaat, mag fitOnce opnieuw
      }
    } else {
      elLat.textContent = "—";
      elLon.textContent = "—";
      elSpeed.textContent = "—";
    }
  } catch (e) {
    elStatus.textContent = "Error: " + e.message;
  }
}
fetchData();
setInterval(fetchData, 2000);

// === Upload vanuit dit device ===
async function postUpdate(lat, lon, speedKmh) {
  await fetch("update.php", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lat, lon,
      speed_kmh: isFinite(speedKmh) ? speedKmh : null,
      timestamp: new Date().toISOString().slice(0, 19).replace("T", " "),
    }),
    cache: "no-store",
  });
}

let watchId = null;
btn.addEventListener("click", () => {
  if (!("geolocation" in navigator)) {
    uploadStatus.textContent = "Geen geolocatie in browser";
    return;
  }
  if (watchId !== null) {
    navigator.geolocation.clearWatch(watchId);
    watchId = null;
    uploadStatus.textContent = "Upload gestopt.";
    btn.textContent = "📡 Start live upload (dit device)";
    return;
  }
  watchId = navigator.geolocation.watchPosition(
    (pos) => {
      const { latitude, longitude, accuracy, speed } = pos.coords;
      const kmh = (typeof speed === "number" && isFinite(speed)) ? speed * 3.6 : null;
      const p = [latitude, longitude];

      if (!meMarker) {
        meMarker = L.marker(p, { title: "Jij" }).addTo(map);
        meAccuracy = L.circle(p, { radius: accuracy }).addTo(map);
      } else {
        meMarker.setLatLng(p);
        meAccuracy.setLatLng(p).setRadius(accuracy);
      }

      myPos = p;
      updateNavLinks();
      updateDistanceAndView();

      postUpdate(latitude, longitude, kmh)
        .then(() => (uploadStatus.textContent = "Live upload actief…"))
        .catch((e) => (uploadStatus.textContent = "Upload fout: " + e.message));
    },
    (err) => (uploadStatus.textContent = "Fout: " + err.message),
    { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 }
  );
  btn.textContent = "⏹️ Stop live upload";
  uploadStatus.textContent = "Live upload starten…";
});