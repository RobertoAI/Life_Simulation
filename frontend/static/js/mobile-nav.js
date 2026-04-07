/* AI Life Simulator - Mobile Navigation */
(function() {
  'use strict';

  if (!('ontouchstart' in window) && window.innerWidth > 768) return;

  const TABS = [
    { label: 'Home', icon: '&#x1F3E0;', href: '/' },
    { label: 'Simulation', icon: '&#x1F30D;', href: '/simulation' },
    { label: 'Agents', icon: '&#x1F9EC;', href: '/agents' },
    { label: 'GPU', icon: '&#x1F4CA;', href: '/gpu' },
    { label: 'Settings', icon: '&#x2699;&#xFE0F;', href: '/settings' },
  ];

  const CURRENT_PAGE = window.location.pathname;

  function createBottomNav() {
    const nav = document.createElement('nav');
    nav.className = 'mobile-bottom-nav';
    nav.id = 'mobile-bottom-nav';
    nav.setAttribute('aria-label', 'Mobile navigation');

    TABS.forEach(tab => {
      const a = document.createElement('a');
      a.href = tab.href;
      a.className = 'mobile-nav-item' + (CURRENT_PAGE === tab.href || (tab.href === '/' && CURRENT_PAGE === '/') ? ' active' : '');
      a.dataset.page = tab.href;
      a.innerHTML = `<span class="mobile-nav-icon">${tab.icon}</span><span class="mobile-nav-label">${tab.label}</span>`;
      nav.appendChild(a);
    });

    document.body.appendChild(nav);
  }

  // Auto-hide on scroll down, show on scroll up
  let lastScrollY = 0;
  let scrollTicking = false;

  function handleScroll() {
    if (!scrollTicking) {
      requestAnimationFrame(() => {
        const nav = document.getElementById('mobile-bottom-nav');
        if (!nav) return;

        const currentY = window.scrollY;
        if (currentY > lastScrollY && currentY > 100) {
          nav.classList.add('hidden');
        } else {
          nav.classList.remove('hidden');
        }
        lastScrollY = currentY;
        scrollTicking = false;
      });
      scrollTicking = true;
    }
  }

  // Swipe detection for page navigation
  let touchStartX = 0;
  let touchStartY = 0;

  function handleTouchStart(e) {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
  }

  function handleTouchEnd(e) {
    const deltaX = e.changedTouches[0].clientX - touchStartX;
    const deltaY = e.changedTouches[0].clientY - touchStartY;

    // Only handle horizontal swipes (deltaX > 50, deltaY < 50)
    if (Math.abs(deltaX) < 50 || Math.abs(deltaY) > Math.abs(deltaX) * 0.6) return;

    const currentPageIndex = TABS.findIndex(t => t.href === CURRENT_PAGE);
    let targetIndex = -1;

    if (deltaX < 0 && currentPageIndex < TABS.length - 1) {
      targetIndex = currentPageIndex + 1;
    } else if (deltaX > 0 && currentPageIndex > 0) {
      targetIndex = currentPageIndex - 1;
    }

    if (targetIndex >= 0) {
      window.location.href = TABS[targetIndex].href;
    }
  }

  // Detect swipe area (bottom 15% of screen)
  function isSwipeArea(e) {
    return e.clientY > window.innerHeight * 0.85;
  }

  // Init
  window.addEventListener('load', () => {
    createBottomNav();
    window.addEventListener('scroll', handleScroll, { passive: true });

    // Touch events for swipe on mobile
    document.addEventListener('touchstart', handleTouchStart, { passive: true });
    document.addEventListener('touchend', handleTouchEnd, { passive: true });
  });

})();
