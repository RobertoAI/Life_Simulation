/* AI Life Simulator - Service Worker Registration */
(function() {
  'use strict';

  if (!('serviceWorker' in navigator)) {
    console.log('[PWA] Service Workers not supported');
    return;
  }

  navigator.serviceWorker.register('/static/sw.js', { scope: '/' })
    .then((registration) => {
      console.log('[PWA] SW registered, scope:', registration.scope);

      // Check for updates
      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            showUpdateToast();
          }
        });
      });
    })
    .catch((err) => {
      console.error('[PWA] SW registration failed:', err);
    });

  // Show update toast
  function showUpdateToast() {
    const existing = document.querySelector('.pwa-update-toast');
    if (existing) return;

    const toast = document.createElement('div');
    toast.className = 'pwa-update-toast';
    toast.innerHTML = `
      <span>New version available! <a href="#" onclick="location.reload(); return false;" style="color:#0d1117;font-weight:bold;text-decoration:underline;">Reload</a></span>
      <button onclick="this.parentElement.style.display='none'" style="background:none;border:none;font-size:1.2rem;cursor:pointer;color:#0d1117;">&times;</button>
    `;
    document.body.appendChild(toast);
  }

  // Offline indicator
  function createOfflineIndicator() {
    const indicator = document.createElement('div');
    indicator.id = 'pwa-offline-indicator';
    indicator.className = navigator.onLine ? 'online' : 'offline';
    indicator.title = navigator.onLine ? 'Online' : 'Offline';
    indicator.setAttribute('aria-label', navigator.onLine ? 'Online' : 'Offline');
    document.body.appendChild(indicator);
  }

  function updateOfflineIndicator() {
    const el = document.getElementById('pwa-offline-indicator');
    if (!el) return;
    if (navigator.onLine) {
      el.className = 'online';
      el.title = 'Online';
      el.setAttribute('aria-label', 'Online');
    } else {
      el.className = 'offline';
      el.title = 'Offline';
      el.setAttribute('aria-label', 'Offline');
    }
  }

  window.addEventListener('load', () => {
    createOfflineIndicator();
  });

  window.addEventListener('online', updateOfflineIndicator);
  window.addEventListener('offline', updateOfflineIndicator);
})();

// Inline styles for toast and indicator
(function() {
  const style = document.createElement('style');
  style.textContent = `
    .pwa-update-toast {
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      background: #2ecc71;
      color: #0d1117;
      padding: 0.75rem 1.25rem;
      border-radius: 8px;
      font-size: 0.9rem;
      font-weight: 600;
      z-index: 10001;
      display: flex;
      align-items: center;
      gap: 0.75rem;
      box-shadow: 0 4px 16px rgba(0,0,0,0.4);
      animation: toastSlideUp 0.3s ease;
    }
    @keyframes toastSlideUp {
      from { bottom: -60px; opacity: 0; }
      to { bottom: 20px; opacity: 1; }
    }
    #pwa-offline-indicator {
      position: fixed;
      top: 10px;
      right: 10px;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      z-index: 9999;
      border: 2px solid rgba(255,255,255,0.3);
      transition: background-color 0.3s;
    }
    #pwa-offline-indicator.online {
      background-color: #2ecc71;
      box-shadow: 0 0 6px #2ecc71;
    }
    #pwa-offline-indicator.offline {
      background-color: #e94560;
      box-shadow: 0 0 6px #e94560;
      animation: offlinePulse 2s infinite;
    }
    @keyframes offlinePulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }
  `;
  document.head.appendChild(style);
})();
