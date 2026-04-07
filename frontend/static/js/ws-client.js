/**
 * ws-client.js - WebSocket client with automatic reconnect.
 */

class SimulationWSClient {
    /**
     * Create a new WebSocket client.
     *
     * @param {string} url - The WebSocket URL (e.g., ws://localhost:8000/ws/simulation).
     * @param {Function} onTick - Callback invoked on each tick message.
     */
    constructor(url, onTick) {
        this.url = url;
        this.onTickCallbacks = [];
        this._ws = null;
        this._reconnectDelay = 1000;
        this._maxReconnectDelay = 10000;
        this._isConnected = false;

        if (onTick) {
            this.onTickCallbacks.push(onTick);
        }
    }

    /** Add a callback for tick events. */
    onTick(callback) {
        this.onTickCallbacks.push(callback);
    }

    /** Connect to the WebSocket server. */
    connect() {
        this._ws = new WebSocket(this.url);

        this._ws.onopen = () => {
            console.log('[WS] Connected');
            this._isConnected = true;
            this._reconnectDelay = 1000;
        };

        this._ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                // Call all registered tick callbacks
                this.onTickCallbacks.forEach((cb) => cb(data));
            } catch (e) {
                console.error('[WS] Error parsing message:', e);
            }
        };

        this._ws.onclose = () => {
            console.log('[WS] Disconnected, reconnecting...');
            this._isConnected = false;
            // Exponential backoff for reconnect
            setTimeout(() => {
                this.connect();
            }, this._reconnectDelay);
            this._reconnectDelay = Math.min(
                this._reconnectDelay * 1.5,
                this._maxReconnectDelay
            );
        };

        this._ws.onerror = (error) => {
            console.error('[WS] Error:', error);
        };
    }

    /** Disconnect manually. */
    disconnect() {
        if (this._ws) {
            this._ws.onclose = null;  // Prevent reconnect
            this._ws.close();
            this._isConnected = false;
        }
    }

    /** Check if currently connected. */
    get isConnected() {
        return this._isConnected && this._ws !== null && this._ws.readyState === WebSocket.OPEN;
    }
}
