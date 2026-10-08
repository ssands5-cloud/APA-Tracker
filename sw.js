/* Ultimate Coach Match Night: offline cache. The package is fetched network-first (a fresh publish
   wins whenever the phone is online) and falls back to the last downloaded copy offline. */
var PREFIX = "uc-match-night-";
var CACHE = PREFIX + "357qA3qUX6rb";
var SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png",
             "icons/apple-touch-icon.png", "package.json"];
self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    // Only this app's own old caches: CacheStorage is shared by every project on ssands5-cloud.github.io.
    return Promise.all(keys.filter(function (k) { return k.indexOf(PREFIX) === 0 && k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;
  var url = new URL(e.request.url);
  if (url.pathname.endsWith("/package.json") || url.pathname.endsWith("/") || url.pathname.endsWith("/index.html")) {
    e.respondWith(fetch(e.request).then(function (r) {
      if (!r.ok) {   // 404/5xx: keep serving the last good copy instead of the error
        return caches.match(e.request, {ignoreSearch: true}).then(function (hit) { return hit || r; });
      }
      var copy = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, copy); }); return r;
    }).catch(function () { return caches.match(e.request, {ignoreSearch: true}); }));
    return;
  }
  e.respondWith(caches.match(e.request).then(function (hit) { return hit || fetch(e.request); }));
});
