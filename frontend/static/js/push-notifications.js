/**
 * Push Notifications Module for AI Life Simulator.
 *
 * Handles Web Push API subscription management, in-app toast
 * notifications, and settings UI integration.
 *
 * Usage:
 *   <script src="/static/js/push-notifications.js"></script>
 *   <script>
 *     const pushMgr = new PushNotificationManager();
 *     pushMgr.init();
 *   </script>
 */
class PushNotificationManager {
    constructor() {
        this.subscription = null;
        this.subscribed = false;
        this.pushEnabled = false;
        this.notificationTypes = {
            ecosystem_collapse: true,
            population_surge: true,
            gpu_temperature: true,
            auto_balance: true,
            stress_test: true
        };
    }

    /** Initialize the push notification system. */
    async init() {
        // Load settings from localStorage if available
        this.pushEnabled = localStorage.getItem('push_notifications_enabled') === 'true';
        const storedTypes = localStorage.getItem('push_notification_types');
        if (storedTypes) {
            try {
                this.notificationTypes = JSON.parse(storedTypes);
            } catch (e) {
                console.warn('Failed to parse stored notification types:', e);
            }
        }

        // Check if Service Worker is already registered
        if ('serviceWorker' in navigator) {
            try {
                const registration = await navigator.serviceWorker.getRegistration('/static/push-sw.js');
                if (registration) {
                    // Check for existing subscription
                    this.subscription = await registration.pushManager.getSubscription();
                    if (this.subscription) {
                        this.subscribed = true;
                    }
                }

                // Listen for push messages to update in-app UI
                navigator.serviceWorker.addEventListener('message', (event) => {
                    if (event.data && event.data.type === 'push_notification') {
                        this.showInAppNotification(
                            event.data.title,
                            event.data.body,
                            event.data.icon
                        );
                    }
                });
            } catch (e) {
                console.warn('Push notification init warning:', e.message);
            }
        }

        // Update settings UI if it exists on page
        this.updateSettingsUI();

        console.log(`Push notifications initialized: enabled=${this.pushEnabled}, subscribed=${this.subscribed}`);
    }

    /**
     * Request permission for push notifications.
     * Returns the permission state string.
     */
    async requestPushPermission() {
        if (!('Notification' in window)) {
            console.warn('This browser does not support notifications');
            return 'unsupported';
        }

        if (Notification.permission === 'granted') {
            return 'granted';
        }

        if (Notification.permission === 'denied') {
            console.warn('Notification permission denied');
            return 'denied';
        }

        const permission = await Notification.requestPermission();
        console.log(`Notification request result: ${permission}`);
        return permission;
    }

    /**
     * Subscribe to push notifications.
     *
     * 1. Requests permission if needed
     * 2. Registers/gets the Service Worker
     * 3. Creates the subscription
     * 4. Sends subscription to server
     *
     * Returns { ok: boolean, error?: string }
     */
    async subscribeToPush() {
        try {
            // Step 1: Get permission
            const permission = await this.requestPushPermission();
            if (permission !== 'granted') {
                this.pushEnabled = false;
                localStorage.setItem('push_notifications_enabled', 'false');
                return { ok: false, error: 'Permission not granted' };
            }

            // Step 2: Register Service Worker
            let registration;
            if ('serviceWorker' in navigator) {
                registration = await navigator.serviceWorker.register('/static/push-sw.js');
                // Wait for SW to be ready
                await navigator.serviceWorker.ready;
            } else {
                return { ok: false, error: 'Service Workers not supported' };
            }

            // Step 3: Create subscription
            this.subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: await this.getVapidPublicKey()
            });

            const subData = this.subscription.toJSON();

            // Step 4: Send to server
            const response = await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(subData)
            });

            const result = await response.json();

            if (result.ok) {
                this.subscribed = true;
                this.pushEnabled = true;
                localStorage.setItem('push_notifications_enabled', 'true');
                this.showInAppNotification(
                    'Push Notifications Enabled',
                    'You will now receive real-time alerts',
                    '✅'
                );
                this.updateSettingsUI();
                return { ok: true, id: result.id };
            } else {
                return { ok: false, error: result.error };
            }
        } catch (error) {
            console.error('Subscribe error:', error);
            return { ok: false, error: error.message };
        }
    }

    /**
     * Unsubscribe from push notifications.
     *
     * Removes browser subscription and deactivates on server.
     * Returns { ok: boolean, error?: string }
     */
    async unsubscribeFromPush() {
        try {
            if (this.subscription) {
                await this.subscription.unsubscribe();
            }

            if (this.subscription) {
                const subData = this.subscription.toJSON();
                // Server-side remove
                await fetch('/api/push/unsubscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(subData)
                });
            }

            this.subscription = null;
            this.subscribed = false;
            this.pushEnabled = false;
            localStorage.setItem('push_notifications_enabled', 'false');
            this.showInAppNotification(
                'Push Notifications Disabled',
                'You will no longer receive push alerts',
                '❌'
            );
            this.updateSettingsUI();
            return { ok: true };
        } catch (error) {
            console.error('Unsubscribe error:', error);
            // Still try to deactivate locally
            this.subscribed = false;
            this.pushEnabled = false;
            localStorage.setItem('push_notifications_enabled', 'false');
            this.updateSettingsUI();
            return { ok: false, error: error.message };
        }
    }

    /**
     * Send a test notification request to the server.
     */
    async sendTestNotification() {
        try {
            const response = await fetch('/api/push/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            const result = await response.json();
            if (result.ok) {
                this.showInAppNotification(
                    'Test Sent',
                    `Notification sent to ${result.sent} subscriber(s)`,
                    '📨'
                );
            } else {
                this.showInAppNotification('Test Failed', result.error || 'Unknown error', '⚠️');
            }
        } catch (error) {
            this.showInAppNotification('Test Error', error.message, '⚠️');
        }
    }

    /**
     * Show an in-app toast-style notification.
     * Creates a DOM element that auto-dismisses after 5 seconds.
     */
    showInAppNotification(title, body, icon = '📌') {
        // Create toast container if it doesn't exist
        let container = document.getElementById('push-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'push-toast-container';
            container.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                display: flex;
                flex-direction: column;
                gap: 10px;
            `;
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.style.cssText = `
            background: #1a1a2e;
            color: #eee;
            padding: 12px 18px;
            border-radius: 8px;
            border-left: 4px solid #4CAF50;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            min-width: 250px;
            max-width: 350px;
            font-family: 'Inter', sans-serif;
            font-size: 14px;
            animation: pushToastSlide 0.3s ease-out;
        `;

        toast.innerHTML = `
            <div style="display: flex; align-items: flex-start; gap: 10px;">
                <span style="font-size: 18px;">${icon}</span>
                <div style="flex: 1;">
                    <div style="font-weight: 600; margin-bottom: 4px;">${this.escapeHtml(title)}</div>
                    <div style="opacity: 0.85; font-size: 12px;">${this.escapeHtml(body)}</div>
                </div>
                <button onclick="this.parentElement.parentElement.remove()"
                    style="background: none; border: none; color: #999; cursor: pointer; font-size: 16px; padding: 0;">&times;</button>
            </div>
        `;

        container.appendChild(toast);

        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    /**
     * Fetch the VAPID public key from server for encryption.
     * For now returns a placeholder -- the server should expose
     * the VAPID public key via an endpoint.
     */
    async getVapidPublicKey() {
        try {
            const response = await fetch('/api/push/vapid-public-key');
            if (response.ok) {
                const data = await response.json();
                return this.urlB64ToUint8Array(data.publicKey);
            }
        } catch (e) {
            console.warn('Could not fetch VAPID public key from server:', e);
        }
        // Fallback: return a default key (should match server)
        console.warn('Using default VAPID public key placeholder');
        return this.urlB64ToUint8Array(
            'BKgHn5gQ6xY5m2V1cK2gJ5mN7qX8tR4wE9iO3pL6sU1vW2xC8yB0dF5eG7hJ9kLmN3pQ6sT8vX0zB2dE4fH6gI9jKlMnOpQrRsTuVwXyZbC2'
        );
    }

    /**
     * Convert a URL-safe base64 string to a Uint8Array.
     */
    urlB64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    /**
     * Save notification type preferences to localStorage.
     */
    saveNotificationPreferences() {
        localStorage.setItem('push_notification_types', JSON.stringify(this.notificationTypes));
    }

    /**
     * Update the settings page UI to reflect current subscription state.
     */
    updateSettingsUI() {
        const toggle = document.getElementById('push-enabled-toggle');
        const subscribeBtn = document.getElementById('subscribe-btn');
        const unsubscribeBtn = document.getElementById('unsubscribe-btn');
        const statusEl = document.getElementById('push-status');
        const testBtn = document.getElementById('test-push-btn');

        // Update toggle
        if (toggle) {
            toggle.checked = this.pushEnabled;
        }

        // Update buttons visibility
        if (subscribeBtn) {
            subscribeBtn.style.display = this.subscribed ? 'none' : '';
            subscribeBtn.disabled = !this.pushEnabled;
        }
        if (unsubscribeBtn) {
            unsubscribeBtn.style.display = this.subscribed ? '' : 'none';
        }

        // Update status text
        if (statusEl) {
            if (!('Notification' in window)) {
                statusEl.textContent = '⚠️ Notifications not supported in this browser';
                statusEl.style.color = '#f59e0b';
            } else if (Notification.permission === 'denied') {
                statusEl.textContent = '❌ Notifications blocked in browser settings';
                statusEl.style.color = '#ef4444';
            } else if (this.subscribed) {
                statusEl.textContent = '✅ Subscribed and receiving notifications';
                statusEl.style.color = '#4CAF50';
            } else if (this.pushEnabled) {
                statusEl.textContent = '⏳ Click Subscribe to start receiving push notifications';
                statusEl.style.color = '#3b82f6';
            } else {
                statusEl.textContent = '🔇 Push notifications are disabled';
                statusEl.style.color = '#999';
            }
        }

        // Checkboxes
        for (const [type, enabled] of Object.entries(this.notificationTypes)) {
            const cb = document.getElementById(`notif-${type}`);
            if (cb) {
                cb.checked = enabled;
            }
        }

        // Test button
        if (testBtn) {
            testBtn.disabled = !this.subscribed;
        }
    }

    /**
     * Simple HTML escaping to prevent XSS.
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }
}

/* ---- Auto-initialise if settings page ---- */
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('push-section')) {
        window.pushManager = new PushNotificationManager();
        window.pushManager.init();
    }
});
