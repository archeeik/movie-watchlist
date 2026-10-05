/* 보고싶은 영화 — 서비스 워커
   앱 파일과 data/*.json 모두 항상 새로 받고, 연결이 안 될 때만 저장해 둔 것을 쓴다(고친 내용이 바로 반영되게).
   포스터 등 다른 사이트의 파일은 건드리지 않는다. */
const CACHE = "movies-v1";
const SHELL = ["./", "style.css", "app.js", "manifest.webmanifest", "icons/icon-192.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  const put = res => { if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); } return res; };
  e.respondWith(fetch(req, { cache: "no-cache" }).then(put).catch(() => caches.match(req, { ignoreSearch: true })));
});
