// service-worker.js
const CACHE = "tracker-v3";

// basispad automatisch bepalen, bv. /TrackerApp/
const BASE = self.registration.scope.replace(location.origin, "").replace(/\/+$/, "") + "/";

const PRECACHE = [
  BASE,                    // /
  BASE + "index.html",
  BASE + "app.js",
  BASE + "style.css",
  BASE + "leaflet/leaflet.css",
  // icons optioneel: voeg ze pas toe als ze echt bestaan
  // BASE + "icons/icon-192.png",
  // BASE + "icons/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      for (const url of PRECACHE) {
        try {
          const resp = await fetch(url, { cache: "no-store" });
          if (resp.ok) await cache.put(url, resp);
          // sla silently over als 404/500
        } catch (err) {
          // negeer netwerkfouten tijdens precache
        }
      }
    })()
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// data.json / update.php nooit uit cache; rest: cache-first met netwerk fallback
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.endsWith("/data.json") || url.pathname.endsWith("/update.php")) {
    return; // laat netwerk
  }
  if (url.pathname.startsWith(BASE)) {
    e.respondWith(
      caches.match(e.request).then(cached => {
        if (cached) return cached;
        return fetch(e.request).then(resp => {
          if (resp.ok && e.request.method === "GET") {
            const copy = resp.clone();
            caches.open(CACHE).then(c => c.put(e.request, copy));
          }
          return resp;
        });
      })
    );
  }
});