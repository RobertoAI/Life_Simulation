/** Service Worker for Push Notifications.
 *
 * Handles incoming push events, displays notifications,
 * and routes notification clicks.
 */

self.addEventListener('push', (event) => {
  let title = 'AI Life Simulator';
  let body = 'New notification';
  let icon = '/static/images/icon.png';
  let url = '/';

  try {
    // Try to parse the encrypted payload
    const data = event.data ? event.data.json() : {};
    if (data.title) title = data.title;
    if (data.body) body = data.body;
    if (data.icon) icon = data.icon;
    if (data.url) url = data.url;
  } catch (e) {
    // If JSON body wasn't available, use a default
    console.log('Push event received (raw data not parseable as JSON):', e.message);
  }

  event.waitUntil(
    self.registration.showNotification(title, {
      body: body,
      icon: icon,
      badge: icon,
      tag: 'notif-simulation',
      renotify: true,
      data: { url: url },
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const url = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Find existing client to focus
      for (const client of clientList) {
        if (client.url.includes(url) && 'focus' in client) {
          return client.focus();
        }
      }
      // Open new window
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});

self.addEventListener('pushsubscriptionchange', (event) => {
  // Re-subscribe when the subscription changes
  const endpoint = '/api/push/subscribe';
  event.waitUntil(
    fetch('/api/push/resubscribe', { method: 'POST', body: '{}' })
  );
});
