const CACHE_NAME = 'tankly-static-v6';
const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/logo.png?v=3',
  '/static/app.css?v=10',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/vendor/alpine.min.js',
  '/static/vendor/tailwindcss.js',
  '/static/vendor/chart.umd.min.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => Promise.all(
      cacheNames
        .filter((cacheName) => cacheName !== CACHE_NAME)
        .map((cacheName) => caches.delete(cacheName))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);
  const isStaticAsset = requestUrl.origin === self.location.origin
    && requestUrl.pathname.startsWith('/static/');

  if (!isStaticAsset) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => (
      cachedResponse || fetch(event.request)
    ))
  );
});
