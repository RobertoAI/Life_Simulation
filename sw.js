/* Service Worker for AI Life Simulator - Offline Support */

const CACHE_NAME = 'life-sim-v1';
const OFFLINE_CACHE = 'offline-html';
const OFFLINE_PAGE = '/offline.html';

const OFFLINE_CSS = '/static/css/offline.css';

// Pages that should be cached for offline
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/css/mobile-optimizations.css',
    '/static/css/accessibility.css',
    '/static/css/offline.css',
    '/static/js/touch-gestures.js',
    OFFLINE_PAGE
];

// Install event: cache offline page and static assets
self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(OFFLINE_CACHE).then(function (cache) {
            return cache.addAll(STATIC_ASSETS);
        }).catch(function (err) {
            console.log('SW install cache failed:', err);
        })
    );
    self.skipWaiting();
});

// Activate event: clean old caches
self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (cacheNames) {
            return Promise.all(
                cacheNames.filter(function (cacheName) {
                    return cacheName !== CACHE_NAME && cacheName !== OFFLINE_CACHE;
                }).map(function (cacheName) {
                    return caches.delete(cacheName);
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch event: network first with cache fallback
self.addEventListener('fetch', function (event) {
    const request = event.request;
    const url = new URL(request.url);

    // For navigation requests (HTML pages)
    if (request.mode === 'navigate' || (request.method === 'GET' && request.headers.get('accept').includes('text/html'))) {
        event.respondWith(networkFirstWithOfflineFallback(request));
        return;
    }

    // For API requests
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(cacheLatestApiResponse(request));
        return;
    }

    // For static assets: cache first
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(cacheFirst(request));
        return;
    }

    // Default: network first
    event.respondWith(fetch(request).catch(function () {
        return caches.match(OFFLINE_PAGE);
    }));
});

// Network first strategy with offline fallback
async function networkFirstWithOfflineFallback(request) {
    try {
        const response = await fetch(request);
        const responseClone = response.clone();

        // Cache the successful response
        caches.open(CACHE_NAME).then(function (cache) {
            cache.put(request, responseClone);
        });

        // Cache API responses for offline use
        if (request.url.includes('/api/simulation/status')) {
            cacheApiResponseForOffline(request, responseClone);
        }

        return response;
    } catch (error) {
        // Network failed - try cache first
        const cached = await caches.match(request);
        if (cached) return cached;

        // Last resort: offline page
        const offlineResponse = await caches.match(OFFLINE_PAGE);
        if (offlineResponse) return offlineResponse;

        // Create offline response if not cached
        return new Response(
            '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Offline</title></head>' +
            '<body style="background:#1a1a2e;color:#e4e4e4;font-family:sans-serif;text-align:center;padding:2rem;">' +
            '<h1 style="color:#e94560;">You\'re Offline</h1><p>Please check your connection.</p>' +
            '<button onclick="location.reload()">Retry</button></body></html>',
            { headers: { 'Content-Type': 'text/html' } }
        );
    }
}

// Cache latest API responses for offline dashboard
async function cacheLatestApiResponse(request) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            const responseClone = response.clone();
            cacheApiResponseForOffline(request, responseClone);
        }
        return response;
    } catch (error) {
        // Return cached API response or empty JSON
        const cached = await getCachedApiResponse(request.url);
        if (cached) return cached;

        return new Response(
            JSON.stringify({ error: 'offline', cached: true }),
            {
                headers: { 'Content-Type': 'application/json' },
                status: 200
            }
        );
    }
}

// Store API response in IndexedDB for offline access
function cacheApiResponseForOffline(request, response) {
    try {
        response.clone().json().then(function (data) {
            const dbReq = indexedDB.open('offline-store', 1);
            dbReq.onupgradeneeded = function (event) {
                const db = event.target.result;
                if (!db.objectStoreNames.contains('offline-cache')) {
                    db.createObjectStore('offline-cache', { keyPath: 'id' });
                }
            };
            dbReq.onsuccess = function (event) {
                const db = event.target.result;
                const tx = db.transaction('offline-cache', 'readwrite');
                const store = tx.objectStore('offline-cache');
                data.id = 'simulation-status';
                data.timestamp = Date.now();
                store.put(data);
            };
            dbReq.onerror = function () {
                console.log('Failed to cache API response');
            };
        }).catch(function () {
            // Non-JSON response, skip caching
        });
    } catch (e) {
        console.log('Error caching API response:', e);
    }
}

// Retrieve cached API response from IndexedDB
async function getCachedApiResponse(url) {
    return new Promise(function (resolve) {
        const dbReq = indexedDB.open('offline-store', 1);
        dbReq.onsuccess = function (event) {
            const db = event.target.result;
            if (!db.objectStoreNames.contains('offline-cache')) {
                resolve(null);
                return;
            }
            const tx = db.transaction('offline-cache', 'readonly');
            const store = tx.objectStore('offline-cache');
            const getReq = store.get('simulation-status');
            getReq.onsuccess = function () {
                if (getReq.result) {
                    resolve(new Response(JSON.stringify(getReq.result), {
                        headers: { 'Content-Type': 'application/json' }
                    }));
                } else {
                    resolve(null);
                }
            };
            getReq.onerror = function () {
                resolve(null);
            };
        };
        dbReq.onerror = function () {
            resolve(null);
        };
    });
}

// Cache-first strategy for static assets
async function cacheFirst(request) {
    const cached = await caches.match(request);
    if (cached) return cached;

    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch (error) {
        return new Response('', { status: 408 });
    }
}

// Message handler for manual cache updates
self.addEventListener('message', function (event) {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }

    if (event.data && event.data.type === 'CACHE_API') {
        cacheApiResponseForOffline(event.data.request, event.data.response);
    }
});
