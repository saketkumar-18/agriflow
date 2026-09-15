/* AgriFlow service worker — app shell + cached last-known API GETs.
 * Strategy:
 *  - Same-origin navigations & static assets: network-first, fall back to
 *    cache (app shell works offline).
 *  - API GET responses (JSON): cache the latest successful response per URL
 *    (stale-while-revalidate); served when the network fails.
 *  - API non-GETs: pass through (offline writes are queued by the app via
 *    POST /api/v1/sync/batch when back online).
 */
const VERSION = "agriflow-v1";
const SHELL_CACHE = `${VERSION}-shell`;
const API_CACHE = `${VERSION}-api`;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((c) => c.addAll(["/", "/manifest.webmanifest"]))
      .catch(() => undefined),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))),
      ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  const isApi =
    url.origin !== self.location.origin &&
    (url.pathname.startsWith("/api/v1/") || url.pathname === "/api/health");
  if (isApi) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && res.headers.get("content-type")?.includes("json")) {
            const copy = res.clone();
            caches.open(API_CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(async () => {
          const cached = await caches.match(req);
          return (
            cached ||
            new Response(JSON.stringify({ error: { code: "errors.network", message: "offline", details: null } }), {
              status: 504,
              headers: { "Content-Type": "application/json" },
            })
          );
        }),
    );
    return;
  }

  // Same-origin navigation / assets: network-first with cache fallback.
  if (url.origin === self.location.origin) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(SHELL_CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(async () => {
          const cached = await caches.match(req);
          if (cached) return cached;
          if (req.mode === "navigate") {
            const shell = await caches.match("/");
            if (shell) return shell;
          }
          return new Response("Offline", { status: 503 });
        }),
    );
  }
});
