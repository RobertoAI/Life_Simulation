/* AI Life Simulator - PWA Install Handler */
(function() {
  'use strict';

  let deferredPrompt = null;
  const INSTALL_KEY = 'lifesim_install_state';
  const DEFERRED_TIMEOUT = 30000; // 30 seconds

  function getInstallState() {
    try {
      return JSON.parse(localStorage.getItem(INSTALL_KEY) || '{}');
    } catch (e) {
      return {};
    }
  }

  function setInstallState(state) {
    try {
      localStorage.setItem(INSTALL_KEY, JSON.stringify(state));
    } catch (e) { /* noop */ }
  }

  // Track beforeinstallprompt event
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredPrompt = event;
    const state = getInstallState();

    // If already installed or deferred permanently, don't show
    if (state.installed || state.deferred_forever) return;

    // Show install prompt after delay
    setTimeout(() => {
      showInstallBanner();
    }, DEFERRED_TIMEOUT);
  });

  function showInstallBanner() {
    const state = getInstallState();
    if (state.deferred) {
      // Show again only once after deferral
      if (state.deferred_count && state.deferred_count >= 3) return;
    }

    if (document.querySelector('.pwa-install-banner')) return;

    const banner = document.createElement('div');
    banner.className = 'pwa-install-banner';
    banner.innerHTML = `
      <div class="pwa-install-content">
        <div class="pwa-install-icon">&#x1F4F1;</div>
        <div class="pwa-install-text">
          <strong>Install LifeSim</strong>
          <span>Get quick access to the AI Life Simulator from your home screen.</span>
        </div>
        <div class="pwa-install-actions">
          <button class="pwa-install-btn install">Install</button>
          <button class="pwa-install-btn later">Later</button>
        </div>
      </div>
    `;
    document.body.appendChild(banner);

    // Install button
    banner.querySelector('.install').addEventListener('click', async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      console.log('[PWA] Install prompt outcome:', outcome);
      if (outcome === 'accepted') {
        setInstallState({ installed: true });
        showToast('LifeSim installed!');
      } else {
        const s = getInstallState();
        setInstallState({ deferred: true, deferred_count: (s.deferred_count || 0) + 1 });
      }
      banner.remove();
      deferredPrompt = null;
    });

    // Later button
    banner.querySelector('.later').addEventListener('click', () => {
      const s = getInstallState();
      setInstallState({ deferred: true, deferred_count: (s.deferred_count || 0) + 1, deferred_forever: true });
      banner.remove();
    });
  }

  // Detect when app is installed
  window.addEventListener('appinstalled', (event) => {
    console.log('[PWA] App was installed');
    setInstallState({ installed: true });
    showToast('LifeSim installed!');
    deferredPrompt = null;
    const banner = document.querySelector('.pwa-install-banner');
    if (banner) banner.remove();
  });

  // Show toast notification
  function showToast(message) {
    const existing = document.querySelector('.pwa-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'pwa-toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(20px)';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // Add toast styles
  (function() {
    const style = document.createElement('style');
    style.textContent = `
      .pwa-install-banner {
        position: fixed;
        bottom: 80px;
        left: 12px;
        right: 12px;
        background: var(--bg-card, #0f3460);
        border: 1px solid var(--border-color, #1a3a5c);
        border-radius: 12px;
        z-index: 10000;
        box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        animation: pwaBannerSlide 0.4s ease;
        max-width: 400px;
        margin: 0 auto;
        left: 50%;
        transform: translateX(-50%);
      }
      @keyframes pwaBannerSlide {
        from { transform: translateX(-50%) translateY(100%); opacity: 0; }
        to { transform: translateX(-50%) translateY(0); opacity: 1; }
      }
      .pwa-install-content {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 1rem;
      }
      .pwa-install-icon {
        font-size: 2rem;
        flex-shrink: 0;
      }
      .pwa-install-text {
        flex: 1;
        min-width: 0;
      }
      .pwa-install-text strong {
        display: block;
        color: var(--text-primary, #e4e4e4);
        font-size: 0.95rem;
      }
      .pwa-install-text span {
        color: var(--text-secondary, #a0a0b0);
        font-size: 0.8rem;
      }
      .pwa-install-actions {
        display: flex;
        gap: 0.5rem;
        flex-shrink: 0;
      }
      .pwa-install-btn {
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.85rem;
        font-weight: 600;
        min-height: 36px;
      }
      .pwa-install-btn.install {
        background: #e94560;
        color: #fff;
      }
      .pwa-install-btn.later {
        background: transparent;
        color: var(--text-secondary, #a0a0b0);
        border: 1px solid var(--border-color, #1a3a5c);
      }
      .pwa-toast {
        position: fixed;
        bottom: 100px;
        left: 50%;
        transform: translateX(-50%);
        background: #2ecc71;
        color: #0d1117;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-weight: 700;
        font-size: 0.95rem;
        z-index: 10002;
        box-shadow: 0 4px 16px rgba(0,0,0,0.4);
        transition: opacity 0.3s, transform 0.3s;
      }
      @media (max-width: 420px) {
        .pwa-install-content {
          flex-wrap: wrap;
        }
        .pwa-install-actions {
          width: 100%;
          justify-content: flex-end;
          margin-top: 0.5rem;
        }
      }
    `;
    document.head.appendChild(style);
  })();

})();
