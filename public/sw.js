/* A network-only service worker keeps the authenticated PWA installable without
   retaining protected pages, API responses, telemetry, or credentials. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) =>
  event.waitUntil(self.clients.claim()),
);
