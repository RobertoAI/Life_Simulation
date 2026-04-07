// Touch Gestures and Mobile Interactions

(function () {
    'use strict';

    // Page order for swipe navigation
    const PAGE_ORDER = [
        '/simulation',
        '/gpu',
        '/analytics',
        '/settings'
    ];

    const SWIPE_THRESHOLD = 60;
    const TAP_THRESHOLD = 300;
    const LONG_PRESS_DURATION = 500;

    let touchStartX = 0;
    let touchStartY = 0;
    let touchStartTime = 0;
    let longPressTimer = null;
    let isLongPress = false;

    // Prevent default touch behaviors that interfere with the app
    function preventPullToRefresh(e) {
        // Only prevent if not scrolling within a scrollable container
        const target = e.target;
        const scrollableParent = target.closest('.agents-table-container, .analytics-tabs, [data-scrollable]');
        if (!scrollableParent) {
            // Don't prevent on canvas (it has its own handling)
            if (target.tagName !== 'CANVAS') {
                return;
            }
        }
    }

    document.addEventListener('touchmove', function (e) {
        // Prevent pull-to-refresh
        if (document.body.scrollTop === 0 && e.touches[0].clientY > touchStartY) {
            // Allow within scrollable containers
            const scrollableParent = e.target.closest('.agents-table-container, .analytics-tabs');
            if (!scrollableParent) {
                // Only prevent if actually at the top
                if (window.scrollY === 0) {
                    // We still want scroll, so let it pass
                }
            }
        }
    }, { passive: false });

    // Swipe navigation
    function getCurrentPageIndex() {
        const currentPath = window.location.pathname;
        return PAGE_ORDER.indexOf(currentPath);
    }

    function navigateToPage(index) {
        if (index >= 0 && index < PAGE_ORDER.length) {
            window.location.href = PAGE_ORDER[index];
        }
    }

    // Track touch start for swipe detection
    document.addEventListener('touchstart', function (e) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchStartTime = Date.now();
        isLongPress = false;

        // Long press detection on simulation canvas
        if (e.target.id === 'world-canvas') {
            longPressTimer = setTimeout(function () {
                isLongPress = true;
                handleLongPressOnCanvas(e);
            }, LONG_PRESS_DURATION);
        }
    }, { passive: true });

    document.addEventListener('touchmove', function (e) {
        // Cancel long press if finger moves significantly
        if (longPressTimer && isLongPress === false) {
            const dx = Math.abs(e.touches[0].clientX - touchStartX);
            const dy = Math.abs(e.touches[0].clientY - touchStartY);
            if (dx > 15 || dy > 15) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
        }
    }, { passive: true });

    document.addEventListener('touchend', function (e) {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }

        if (isLongPress) {
            isLongPress = false;
            return;
        }

        const touchEndX = e.changedTouches[0].clientX;
        const touchEndY = e.changedTouches[0].clientY;
        const deltaX = touchEndX - touchStartX;
        const deltaY = touchEndY - touchStartY;
        const deltaTime = Date.now() - touchStartTime;

        // Horizontal swipe detection (horizontal movement dominates)
        if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > SWIPE_THRESHOLD) {
            const currentIndex = getCurrentPageIndex();
            if (currentIndex >= 0) {
                if (deltaX < 0 && currentIndex < PAGE_ORDER.length - 1) {
                    // Swipe left - next page
                    e.preventDefault();
                    navigateToPage(currentIndex + 1);
                } else if (deltaX > 0 && currentIndex > 0) {
                    // Swipe right - previous page
                    e.preventDefault();
                    navigateToPage(currentIndex - 1);
                }
            }
        }
    }, { passive: false });

    // Double tap detection on canvas for centering map
    let lastTapTime = 0;
    let lastTapTarget = null;

    document.addEventListener('touchend', function (e) {
        const now = Date.now();
        const target = e.target;

        if (target.id === 'world-canvas' && lastTapTarget === target) {
            const timeDiff = now - lastTapTime;
            if (timeDiff < TAP_THRESHOLD && timeDiff > 0) {
                handleDoubleTapOnCanvas(e);
                e.preventDefault();
            }
        }

        lastTapTime = now;
        lastTapTarget = target;
    });

    // Handle long press on simulation canvas
    function handleLongPressOnCanvas(e) {
        const canvas = document.getElementById('world-canvas');
        if (!canvas) return;

        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;

        const x = Math.floor((e.changedTouches[0].clientX - rect.left) * scaleX);
        const y = Math.floor((e.changedTouches[0].clientY - rect.top) * scaleY);

        showAgentInfo(x, y);
    }

    // Show agent info popup for long press
    function showAgentInfo(x, y) {
        // Remove existing popup
        const existing = document.getElementById('agent-info-popup');
        if (existing) existing.remove();

        const popup = document.createElement('div');
        popup.id = 'agent-info-popup';
        popup.setAttribute('role', 'tooltip');
        popup.setAttribute('aria-live', 'polite');
        popup.style.cssText = `
            position: fixed;
            background: var(--bg-card, #0f3460);
            border: 1px solid var(--border-color, #1a3a5c);
            border-radius: 8px;
            padding: 12px 16px;
            color: var(--text-primary, #e4e4e4);
            z-index: 10000;
            font-size: 14px;
            max-width: 200px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        `;

        const canvas = document.getElementById('world-canvas');
        const rect = canvas.getBoundingClientRect();
        popup.style.left = Math.min(e.touches ? e.touches[0].clientX : 100, window.innerWidth - 220) + 'px';
        popup.style.top = Math.max((e.touches ? e.touches[0].clientY : 50) - 100, 60) + 'px';

        // Query API for agent at position or show current state
        fetch('/api/simulation/status')
            .then(r => r.json())
            .then(data => {
                popup.innerHTML = `
                    <strong>Location: (${x}, ${y})</strong><br>
                    <span style="color: var(--text-secondary, #a0a0b0);">
                    Tick: ${data.tick ?? '--'}<br>
                    Status: ${data.status ?? 'unknown'}
                    </span>
                `;
            })
            .catch(() => {
                popup.innerHTML = `
                    <strong>Location: (${x}, ${y})</strong><br>
                    <span style="color: var(--text-secondary, #a0a0b0);">No data available</span>
                `;
            });

        document.body.appendChild(popup);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            if (popup.parentElement) popup.remove();
        }, 3000);

        // Announce for screen readers
        announceToScreenReader(`Agent location ${x}, ${y} queried`);
    }

    // Handle double tap on canvas to center map
    function handleDoubleTapOnCanvas(e) {
        const canvas = document.getElementById('world-canvas');
        if (!canvas) return;

        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;

        const x = Math.floor((e.changedTouches[0].clientX - rect.left) * scaleX);
        const y = Math.floor((e.changedTouches[0].clientY - rect.top) * scaleY);

        // If there's a worldMap object with panTo function
        if (typeof worldMap !== 'undefined' && worldMap.panTo) {
            worldMap.panTo(x, y);
        }

        // Announce for screen readers
        announceToScreenReader(`Map centered on ${x}, ${y}`);
    }

    // Screen reader announcer
    function announceToScreenReader(message) {
        const liveRegion = document.getElementById('live-status');
        if (liveRegion) {
            liveRegion.textContent = ''; // Clear first so repeat announcements work
            setTimeout(() => { liveRegion.textContent = message; }, 50);
        }
    }

    // Initialize accessibility toolbar
    document.addEventListener('DOMContentLoaded', function () {
        // High contrast toggle
        const contrastBtn = document.getElementById('toggle-contrast');
        if (contrastBtn) {
            if (localStorage.getItem('highContrast') === 'true') {
                document.body.classList.add('high-contrast');
                contrastBtn.classList.add('active');
            }
            contrastBtn.addEventListener('click', function (e) {
                e.preventDefault();
                document.body.classList.toggle('high-contrast');
                const isOn = document.body.classList.contains('high-contrast');
                localStorage.setItem('highContrast', isOn);
                contrastBtn.classList.toggle('active');
                announceToScreenReader('High contrast ' + (isOn ? 'enabled' : 'disabled'));
            });
        }

        // Large text toggle
        const largeTextBtn = document.getElementById('toggle-large-text');
        if (largeTextBtn) {
            if (localStorage.getItem('largeText') === 'true') {
                document.body.classList.add('large-text');
                largeTextBtn.classList.add('active');
            }
            largeTextBtn.addEventListener('click', function (e) {
                e.preventDefault();
                document.body.classList.toggle('large-text');
                const isOn = document.body.classList.contains('large-text');
                localStorage.setItem('largeText', isOn);
                largeTextBtn.classList.toggle('active');
                announceToScreenReader('Large text ' + (isOn ? 'enabled' : 'disabled'));
            });
        }

        // Reduced motion toggle
        const motionBtn = document.getElementById('toggle-motion');
        if (motionBtn) {
            if (localStorage.getItem('reducedMotion') === 'true') {
                document.body.classList.add('reduced-motion');
                motionBtn.classList.add('active');
            }
            motionBtn.addEventListener('click', function (e) {
                e.preventDefault();
                document.body.classList.toggle('reduced-motion');
                const isOn = document.body.classList.contains('reduced-motion');
                localStorage.setItem('reducedMotion', isOn);
                motionBtn.classList.toggle('active');
                announceToScreenReader('Reduced motion ' + (isOn ? 'enabled' : 'disabled'));
            });
        }
    });

    // Expose functions globally for use by other scripts
    window.announceToScreenReader = announceToScreenReader;

})();
