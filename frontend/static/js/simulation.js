/**
 * simulation.js - Simulation page logic.
 * Handles canvas rendering, WebSocket communication, and API calls.
 */

// Configuration - will be overridden by settings from the backend
const CONFIG = {
    width: 200,
    height: 200,
};

let wsClient = null;
let showHeatmap = false;
let currentTerrain = null;
let currentResources = null;
let agentCanvas = null;

document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('world-canvas');
    const statusEl = document.getElementById('sim-status');
    const statusText = document.getElementById('status-text');
    const tickEl = document.getElementById('tick-count');
    const speedEl = document.getElementById('speed-value');
    const agentCountEl = document.getElementById('agent-count');

    if (!canvas) return;  // Safety check

    // Create overlay canvas for agents
    agentCanvas = document.createElement('canvas');
    agentCanvas.id = 'agent-overlay';
    agentCanvas.style.cssText = 'position:absolute; top:0; left:0; pointer-events:none;';
    const container = canvas.parentElement;
    if (container) {
        container.style.position = 'relative';
        container.appendChild(agentCanvas);
    }

    // Load initial map data from REST API
    loadInitialMap(canvas);

    // Connect WebSocket
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/simulation`;

    wsClient = new SimulationWSClient(wsUrl, (data) => {
        // Update status panel
        if (data.data) {
            statusEl.className = `status-badge ${getStatusClass(data.data.status)}`;
            statusText.textContent = data.data.status;
            tickEl.textContent = data.data.tick;
            speedEl.textContent = data.data.speed + 'x';
        }

        // If agents array is in the payload, render them on the overlay
        if (data.agents) {
            renderAgents(agentCanvas, data.agents, CONFIG.width, CONFIG.height);
            if (agentCountEl) {
                agentCountEl.textContent = data.agents.length;
            }
        }

        // If terrain data is in the payload, render it
        if (data.terrain) {
            if (showHeatmap && currentResources) {
                renderHeatmap(canvas, currentResources, CONFIG.width, CONFIG.height);
            } else {
                renderTerrainMap(canvas, currentTerrain, CONFIG.width, CONFIG.height);
            }
        }
    });

    wsClient.connect();

    // Button handlers
    const startBtn = document.getElementById('btn-start');
    const stopBtn = document.getElementById('btn-stop');
    const pauseBtn = document.getElementById('btn-pause');

    if (startBtn) {
        startBtn.addEventListener('click', () => apiCall('/api/simulation/start', 'POST'));
    }
    if (stopBtn) {
        stopBtn.addEventListener('click', () => apiCall('/api/simulation/stop', 'POST'));
    }
    if (pauseBtn) {
        pauseBtn.addEventListener('click', () => apiCall('/api/simulation/pause', 'POST'));
    }

    // Heatmap toggle
    const heatmapCheckbox = document.getElementById('heatmap-toggle');
    if (heatmapCheckbox) {
        heatmapCheckbox.addEventListener('change', (e) => {
            showHeatmap = e.target.checked;
            if (showHeatmap && currentResources) {
                renderHeatmap(canvas, currentResources, CONFIG.width, CONFIG.height);
            } else if (currentTerrain) {
                renderTerrainMap(canvas, currentTerrain, CONFIG.width, CONFIG.height);
            }
        });
    }

    // Speed buttons
    document.querySelectorAll('.speed-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            const speed = parseFloat(btn.dataset.speed);
            apiCall(`/api/simulation/speed?speed=${speed}`, 'POST');
            // Update active state
            document.querySelectorAll('.speed-btn').forEach((b) => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    // Set initial active speed button to 1x
    const speedOne = document.querySelector('.speed-btn[data-speed="1"]');
    if (speedOne) speedOne.classList.add('active');
});

/**
 * Load the initial terrain map from the REST API.
 */
async function loadInitialMap(canvas) {
    try {
        const response = await fetch('/api/simulation/map');
        const data = await response.json();
        currentTerrain = data.terrain;
        currentResources = data.resources;
        CONFIG.width = data.width;
        CONFIG.height = data.height;

        if (showHeatmap && currentResources) {
            renderHeatmap(canvas, currentResources, CONFIG.width, CONFIG.height);
        } else {
            renderTerrainMap(canvas, currentTerrain, CONFIG.width, CONFIG.height);
        }
    } catch (error) {
        console.error('Failed to load initial map:', error);
        canvas.width = CONFIG.width;
        canvas.height = CONFIG.height;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, CONFIG.width, CONFIG.height);
    }
}

/**
 * Make a REST API call.
 */
async function apiCall(url, method = 'GET') {
    try {
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
        });
        return await response.json();
    } catch (error) {
        console.error(`API call failed (${url}):`, error);
        return null;
    }
}

/**
 * Get CSS class for a simulation status.
 */
function getStatusClass(status) {
    switch (status) {
        case 'running': return 'status-running';
        case 'stopped': return 'status-stopped';
        case 'paused': return 'status-paused';
        default: return '';
    }
}
