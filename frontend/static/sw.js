/* AI Life Simulator - Service Worker */

const CACHE_NAME = 'lifesim-v1';
const BACKUP_CACHE_NAME = 'lifesim-offline-fallback';

// Static assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/static/css/style.css',
  '/static/css/agent-cards.css',
  '/static/css/dashboard.css',
  '/static/js/agents.js',
  '/static/js/analytics.js',
  '/static/js/canvas-utils.js',
  '/static/js/gpu-dashboard.js',
  '/static/js/settings.js',
  '/static/js/simulation.js',
  '/static/js/ws-client.js',
  '/static/js/pwa-install.js',
  '/static/icons/icon.svg',
  '/static/icons/icon-192.svg',
  '/static/icons/icon-512.svg',
  '/simulation',
  '/agents',
  '/gpu',
  '/analytics',
  '/stress-test',
  '/settings',
];

// Offline fallback HTML
const OFFLINE_FALLBACK_HTML = `<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>LifeSim - Offline</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0d1117;color:#e4e4e4;display:flex;align-items:center;justify-content:center;
min-height:100vh;text-align:center;padding:2rem}
.container{max-width:400px}.icon{font-size:4rem;margin-bottom:1rem}
h1{color:#e94560;margin-bottom:0.5rem}p{color:#a0a0b0;margin-bottom:1.5rem}
button{background:#e94560;color:#fff;border:none;padding:0.75rem 2rem;border-radius:8px;
font-size:1rem;cursor:pointer}
</style></head><body>
<div class="container">
<div class="icon">🧬</div><h1>You're Offline</h1>
<p>The AI Life Simulator needs a connection to run simulations, but cached pages may still be available.</p>
<button onclick="window.location.reload()">Try Again</button>
</div>
<script>
// Try to show cached pages
if(navigator.onLine)window.location.reload();
<\/script></body></html>`;

const OFFLINE_FALLBACK_URL = '/offline.html';

// Install event: cache all static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');

  // Cache static assets
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS).catch((err) => {
          console.warn('[SW] Failed to cache some assets:', err);
        });
      })
      .catch((err) => {
        console.warn('[SW] Cache open failed:', err);
      })
  );

  // Create offline fallback
  event.waitUntil(
    caches.open(BACKUP_CACHE_NAME)
      .then((cache) => {
        const response = new Response(OFFLINE_FALLBACK_HTML, {
          headers: { 'Content-Type': 'text/html; charset=utf-8' }
        });
        return cache.put(OFFLINE_FALLBACK_URL, response);
      })
      .catch((err) => {
        console.warn('[SW] Offline fallback cache failed:', err);
      })
  );

  // Activate immediately
  self.skipWaiting();
});

// Activate event: delete old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => name !== CACHE_NAME && name !== BACKUP_CACHE_NAME)
            .map((name) => {
              console.log('[SW] Deleting old cache:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => {
        // Claim all clients immediately
        return self.clients.claim();
      })
  );
});

// Check if URL is WebSocket
function isWebSocket(url) {
  return url.indexOf('ws:') === 0 || url.indexOf('wss:') === 0 ||
         url.includes('/ws') || url.includes('websocket');
}

// Fetch event: cache-first for static, network-first for API
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // NEVER cache WebSocket connections
  if (isWebSocket(url.href)) {
    return;
  }

  // Skip non-GET requests
  if (event.request.method !== 'GET') {
    // For failed API POST/PUT, store for background sync
    if (url.pathname.startsWith('/api/')) {
      event.waitUntil(storeFailedRequest(event.request));
    }
    return;
  }

  // Static assets and pages: cache-first
  if (url.pathname.startsWith('/static/') || url.pathname === '/' ||
      url.pathname === '/manifest.json' ||
      !url.pathname.startsWith('/api/')) {
    event.respondWith(
      caches.match(event.request)
        .then((cached) => {
          if (cached) {
            return cached;
          }
          // Clone the request and fetch from network, cache the response
          const fetchPromise = fetch(event.request)
            .then((networkResponse) => {
              if (networkResponse && networkResponse.status === 200) {
                const responseClone = networkResponse.clone();
                caches.open(CACHE_NAME).then((cache) => {
                  cache.put(event.request, responseClone);
                });
              }
              return networkResponse;
            })
            .catch(() => {
              // Return offline fallback for HTML requests
              if (event.request.headers.get('accept').includes('text/html')) {
                return caches.match(OFFLINE_FALLBACK_URL);
              }
            });
          return fetchPromise;
        })
    );
    return;
  }

  // API requests: network-first
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          return networkResponse;
        })
        .catch(() => {
          // Return cached API response if available
          return caches.match(event.request).then((cached) => {
            if (cached) return cached;
            return new Response(
              JSON.stringify({ error: 'Offline - request queued for sync' }),
              { headers: { 'Content-Type': 'application/json' }, status: 503 }
            );
          });
        })
    );
    return;
  }
});

// Background Sync: store failed requests and retry
const SYNC_QUEUE_KEY = 'lifesim-sync-queue';

async function storeFailedRequest(request) {
  try {
    const clone = request.clone();
    const body = await clone.clone().text().catch(() => null);
    let queue = [];
    try {
      const stored = await caches.match(SYNC_QUEUE_KEY).then(r => r ? r.json() : []);
      queue = stored;
    } catch(e) {}
    queue.push({
      url: request.url,
      method: request.method,
      body: body,
      timestamp: Date.now()
    });
    const response = new Response(JSON.stringify(queue), {
      headers: { 'Content-Type': 'application/json' }
    });
    const cache = await caches.open(BACKUP_CACHE_NAME);
    await cache.put('sync-queue-' + Date.now(), response);
  } catch(e) {
    // Silently fail
  }
}

// Listen for sync event
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-api-queue') {
    event.waitUntil(replaySyncQueue());
  }
});

async function replaySyncQueue() {
  const cache = await caches.open(BACKUP_CACHE_NAME);
  const keys = await cache.keys();
  const queueKeys = keys.filter(k => k.url.includes('sync-queue-'));

  for (const key of queueKeys) {
    try {
      const response = await cache.match(key);
      const queue = await response.json();
      for (const item of queue) {
        await fetch(item.url, {
          method: item.method,
          headers: { 'Content-Type': 'application/json' },
          body: item.body
        });
      }
      await cache.delete(key);
    } catch(e) {
      console.warn('[SW] Sync replay failed:', e);
    }
  }
}

// Message handler for cache updates
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'CACHE_URLS') {
    event.waitUntil(
      caches.open(CACHE_NAME)
        .then((cache) => cache.addAll(event.data.urls))
    );
  }
});

console.log('[SW] Service worker loaded');
