/**
 * stress-test.js - Stress Test Dashboard for AI Life Simulator.
 * Real-time performance metrics with live charts, WS connections, and canvas rendering.
 */

// ============================================================
// State
// ============================================================
const STRESS_STATE = {
    running: false,
    statusText: 'stopped',       // 'running' | 'stopped' | 'paused'
    tickTimes: [],               // rolling window of last 100 tick times (ms)
    tickTimestamps: [],          // timestamps of last N ticks for FPS calc
    totalTicks: 0,
    startTime: null,
    elapsedTimer: null,

    // Rates (computed per second from WS tick deltas)
    birthsPerTick: 0,
    deathsPerTick: 0,
    lastBirthCount: 0,
    lastDeathCount: 0,
    cumBirths: 0,
    cumDeaths: 0,

    // Chart data windows
    chartTickLabels: [],
    chartTickValues: [],
    chartPopLabels: [],
    chartPopValues: [],
    chartBDWindowLabels: [],
    chartBDBirths: [],
    chartBDDeaths: [],
    currentBDWindow: 0,
    currentBDBirths: 0,
    currentBDDeaths: 0,

    // Chart throttling (max 10 fps)
    lastChartUpdate: 0,
    chartThrottleMs: 100,  // 10 fps max for chart renders

    // Canvas
    canvasWidth: 200,
    canvasHeight: 200,
    currentTerrain: null,
    currentResources: null,
    agentOverlay: null,
    showHeatmap: false,

    // Selected grid size
    gridWidth: 300,
    gridHeight: 300,
    agentCount: 10000,

    // Memory estimate (JS heap if available, otherwise rough estimate)
    memoryMB: 0,

    // Queue size tracking
    queueSize: 0,

    // WS clients
    wsSim: null,
    wsGpu: null,
    wsSimConnected: false,
    wsGpuConnected: false,

    // Charts
    chartTickTime: null,
    chartPopulation: null,
    chartBirthsDeaths: null,
};

// ============================================================
// DOM References (populated on load)
// ============================================================
const DOM = {};

function cacheDom() {
    DOM.agentSlider       = document.getElementById('agent-count-slider');
    DOM.agentDisplay      = document.getElementById('agent-count-display');
    DOM.gridSizeGroup     = document.getElementById('grid-size-group');
    DOM.startBtn          = document.getElementById('btn-stress-start');
    DOM.stopBtn           = document.getElementById('btn-stress-stop');
    DOM.statusEl          = document.getElementById('stress-status');
    DOM.wsSimChip         = document.getElementById('ws-sim-chip');
    DOM.wsGpuChip         = document.getElementById('ws-gpu-chip');

    DOM.metricFps         = document.getElementById('metric-fps');
    DOM.metricAvgTick     = document.getElementById('metric-avg-tick');
    DOM.metricActiveAgents= document.getElementById('metric-active-agents');
    DOM.metricBirths      = document.getElementById('metric-births');
    DOM.metricDeaths      = document.getElementById('metric-deaths');
    DOM.metricNetPop      = document.getElementById('metric-net-pop');
    DOM.gaugeFps          = document.getElementById('gauge-fps');
    DOM.gaugeAvgTick      = document.getElementById('gauge-avg-tick');

    DOM.metricPeakTick    = document.getElementById('metric-peak-tick');
    DOM.metricP50Tick     = document.getElementById('metric-p50-tick');
    DOM.metricP95Tick     = document.getElementById('metric-p95-tick');
    DOM.metricP99Tick     = document.getElementById('metric-p99-tick');
    DOM.metricMemory      = document.getElementById('metric-memory');
    DOM.metricQueueSize   = document.getElementById('metric-queue-size');
    DOM.metricTotalTicks  = document.getElementById('metric-total-ticks');
    DOM.metricElapsed     = document.getElementById('metric-elapsed');

    DOM.canvas            = document.getElementById('stress-world-canvas');
}

// ============================================================
// Initialization
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    cacheDom();
    setupControls();
    setupCanvas();
    setupCharts();
    connectWebSockets();
});

// ============================================================
// Controls Setup
// ============================================================
function setupControls() {
    // Agent count slider
    if (DOM.agentSlider) {
        DOM.agentSlider.addEventListener('input', () => {
            STRESS_STATE.agentCount = parseInt(DOM.agentSlider.value, 10);
            DOM.agentDisplay.textContent = STRESS_STATE.agentCount.toLocaleString() + ' agents';
        });
    }

    // Grid size buttons
    if (DOM.gridSizeGroup) {
        DOM.gridSizeGroup.querySelectorAll('.grid-size-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                DOM.gridSizeGroup.querySelectorAll('.grid-size-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                STRESS_STATE.gridWidth = parseInt(btn.dataset.width, 10);
                STRESS_STATE.gridHeight = parseInt(btn.dataset.height, 10);
            });
        });
    }

    // Start button
    if (DOM.startBtn) {
        DOM.startBtn.addEventListener('click', startStressTest);
    }

    // Stop button
    if (DOM.stopBtn) {
        DOM.stopBtn.addEventListener('click', stopStressTest);
    }
}

// ============================================================
// Canvas Setup
// ============================================================
function setupCanvas() {
    if (!DOM.canvas) return;

    // Create agent overlay canvas
    STRESS_STATE.agentOverlay = document.createElement('canvas');
    STRESS_STATE.agentOverlay.id = 'stress-agent-overlay';
    STRESS_STATE.agentOverlay.style.cssText = 'position:absolute; top:0; left:0; pointer-events:none;';

    const container = DOM.canvas.parentElement;
    if (container) {
        container.style.position = 'relative';
        container.appendChild(STRESS_STATE.agentOverlay);
    }

    // Load initial map
    loadInitialMap();
}

async function loadInitialMap() {
    try {
        const response = await fetch('/api/simulation/map');
        const data = await response.json();
        STRESS_STATE.currentTerrain = data.terrain;
        STRESS_STATE.currentResources = data.resources;
        // Use the loaded dimensions initially
        STRESS_STATE.canvasWidth = data.width || 200;
        STRESS_STATE.canvasHeight = data.height || 200;
        renderTerrain();
    } catch (error) {
        console.error('[Stress] Failed to load initial map:', error);
        if (DOM.canvas) {
            DOM.canvas.width = 200;
            DOM.canvas.height = 200;
            const ctx = DOM.canvas.getContext('2d');
            ctx.fillStyle = '#1a1a2e';
            ctx.fillRect(0, 0, 200, 200);
        }
    }
}

function renderTerrain() {
    if (!DOM.canvas) return;
    const w = STRESS_STATE.canvasWidth;
    const h = STRESS_STATE.canvasHeight;
    DOM.canvas.width = w;
    DOM.canvas.height = h;
    STRESS_STATE.agentOverlay.width = w;
    STRESS_STATE.agentOverlay.height = h;

    if (STRESS_STATE.showHeatmap && STRESS_STATE.currentResources) {
        renderHeatmap(DOM.canvas, STRESS_STATE.currentResources, w, h);
    } else if (STRESS_STATE.currentTerrain) {
        renderTerrainMap(DOM.canvas, STRESS_STATE.currentTerrain, w, h);
    }
}

// ============================================================
// Chart.js Setup
// ============================================================
function setupCharts() {
    if (typeof Chart === 'undefined') {
        console.warn('[Stress] Chart.js not loaded, charts disabled');
        return;
    }

    const chartDefaults = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
            legend: {
                labels: { color: '#a0a0b0', font: { size: 11 } }
            }
        },
        scales: {
            x: {
                ticks: { color: '#a0a0b0', maxTicksLimit: 12, font: { size: 10 } },
                grid: { color: 'rgba(255,255,255,0.05)' }
            },
            y: {
                ticks: { color: '#a0a0b0', font: { size: 10 } },
                grid: { color: 'rgba(255,255,255,0.05)' }
            }
        }
    };

    // Tick Time Chart
    const ctxTick = document.getElementById('chartTickTime');
    if (ctxTick) {
        STRESS_STATE.chartTickTime = new Chart(ctxTick, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Tick Time (ms)',
                    data: [],
                    borderColor: '#e94560',
                    backgroundColor: 'rgba(233, 69, 96, 0.1)',
                    fill: true,
                    tension: 0.2,
                    pointRadius: 0,
                    borderWidth: 1.5
                }]
            },
            options: {
                ...chartDefaults,
                scales: {
                    ...chartDefaults.scales,
                    y: {
                        ...chartDefaults.scales.y,
                        beginAtZero: true
                    }
                }
            }
        });
    }

    // Population Chart
    const ctxPop = document.getElementById('chartPopulation');
    if (ctxPop) {
        STRESS_STATE.chartPopulation = new Chart(ctxPop, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Population',
                    data: [],
                    borderColor: '#2ecc71',
                    backgroundColor: 'rgba(46, 204, 113, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 1.5
                }]
            },
            options: {
                ...chartDefaults,
                scales: {
                    ...chartDefaults.scales,
                    y: {
                        ...chartDefaults.scales.y,
                        beginAtZero: true
                    }
                }
            }
        });
    }

    // Births vs Deaths Chart
    const ctxBD = document.getElementById('chartBirthsDeaths');
    if (ctxBD) {
        STRESS_STATE.chartBirthsDeaths = new Chart(ctxBD, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Births',
                        data: [],
                        backgroundColor: 'rgba(46, 204, 113, 0.7)',
                        borderColor: '#2ecc71',
                        borderWidth: 1
                    },
                    {
                        label: 'Deaths',
                        data: [],
                        backgroundColor: 'rgba(231, 76, 60, 0.7)',
                        borderColor: '#e74c3c',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                ...chartDefaults,
                scales: {
                    ...chartDefaults.scales,
                    x: {
                        ...chartDefaults.scales.x,
                        stacked: false
                    },
                    y: {
                        ...chartDefaults.scales.y,
                        beginAtZero: true
                    }
                }
            }
        });
    }
}

// ============================================================
// Chart Updates (throttled)
// ============================================================
function updateChartsThrottled() {
    const now = performance.now();
    if (now - STRESS_STATE.lastChartUpdate < STRESS_STATE.chartThrottleMs) return;
    STRESS_STATE.lastChartUpdate = now;

    // Tick Time Chart
    if (STRESS_STATE.chartTickTime) {
        STRESS_STATE.chartTickTime.data.labels = STRESS_STATE.chartTickLabels.slice(-100);
        STRESS_STATE.chartTickTime.data.datasets[0].data = STRESS_STATE.chartTickValues.slice(-100);
        STRESS_STATE.chartTickTime.update('none');
    }

    // Population Chart (throttle more aggressively - every 5 charts calls)
    if (STRESS_STATE.chartPopulation) {
        STRESS_STATE.chartPopulation.data.labels = STRESS_STATE.chartPopLabels.slice(-100);
        STRESS_STATE.chartPopulation.data.datasets[0].data = STRESS_STATE.chartPopValues.slice(-100);
        STRESS_STATE.chartPopulation.update('none');
    }

    // Births vs Deaths Chart
    if (STRESS_STATE.chartBirthsDeaths) {
        STRESS_STATE.chartBirthsDeaths.data.labels = STRESS_STATE.chartBDWindowLabels;
        STRESS_STATE.chartBirthsDeaths.data.datasets[0].data = STRESS_STATE.chartBDBirths;
        STRESS_STATE.chartBirthsDeaths.data.datasets[1].data = STRESS_STATE.chartBDDeaths;
        STRESS_STATE.chartBirthsDeaths.update('none');
    }
}

// ============================================================
// Metric Updates
// ============================================================
function updateMetrics() {
    const tickTimes = STRESS_STATE.tickTimes;
    const totalTicks = STRESS_STATE.totalTicks;

    // FPS calculation
    const fps = calculateFPS();
    updateMetricElement(DOM.metricFps, fps.toFixed(1), '');
    // FPS gauge: 0-100fps mapped to 0-100%
    const fpsPct = Math.min(fps / 60 * 100, 100);
    updateMiniGauge(DOM.gaugeFps, fpsPct, getFpsColor(fps));

    // Avg tick time
    const avgTick = totalTicks > 0 ? tickTimes.reduce((a, b) => a + b, 0) / tickTimes.length : 0;
    updateMetricElement(DOM.metricAvgTick, avgTick.toFixed(1), 'ms');
    const avgTickColor = getTickTimeColor(avgTick);
    DOM.metricAvgTick.style.color = avgTickColor;
    // Gauge: cap at 1000ms
    const avgPct = Math.min(avgTick / 1000 * 100, 100);
    updateMiniGauge(DOM.gaugeAvgTick, avgPct, avgTickColor);

    // Active agents
    if (DOM.metricActiveAgents) {
        DOM.metricActiveAgents.textContent = STRESS_STATE.activeAgents != null
            ? STRESS_STATE.activeAgents.toLocaleString()
            : '--';
    }

    // Births/sec, Deaths/sec
    const ticksPerSecond = avgTick > 0 ? 1000 / avgTick : 0;
    const birthsPerSec = STRESS_STATE.cumBirths > 0
        ? (STRESS_STATE.cumBirths / Math.max((Date.now() - STRESS_STATE.startTime) / 1000, 0.1)).toFixed(0)
        : '--';
    const deathsPerSec = STRESS_STATE.cumDeaths > 0
        ? (STRESS_STATE.cumDeaths / Math.max((Date.now() - STRESS_STATE.startTime) / 1000, 0.1)).toFixed(0)
        : '--';
    updateMetricElement(DOM.metricBirths, birthsPerSec, '');
    updateMetricElement(DOM.metricDeaths, deathsPerSec, '');

    // Net population change
    const netPopChange = STRESS_STATE.cumBirths - STRESS_STATE.cumDeaths;
    if (DOM.metricNetPop) {
        const prefix = netPopChange >= 0 ? '+' : '';
        DOM.metricNetPop.textContent = netPopChange !== 0 ? prefix + netPopChange.toLocaleString() : '0';
        DOM.metricNetPop.style.color = netPopChange >= 0 ? 'var(--success)' : '#e74c3c';
    }

    // Percentiles
    if (tickTimes.length > 0) {
        const sorted = [...tickTimes].sort((a, b) => a - b);
        const peak = sorted[sorted.length - 1];
        const p50 = percentile(sorted, 0.50);
        const p95 = percentile(sorted, 0.95);
        const p99 = percentile(sorted, 0.99);

        DOM.metricPeakTick.textContent = peak.toFixed(1);
        DOM.metricP50Tick.textContent = p50.toFixed(1);
        DOM.metricP95Tick.textContent = p95.toFixed(1);
        DOM.metricP99Tick.textContent = p99.toFixed(1);
    }

    // Memory estimate
    if (window.performance && window.performance.memory) {
        STRESS_STATE.memoryMB = (window.performance.memory.usedJSHeapSize / 1048576).toFixed(0);
    } else {
        // Rough estimate based on agent count and tick data
        const agentMemory = STRESS_STATE.agentCount * 0.002; // ~2KB per agent estimate
        const tickBufferMemory = tickTimes.length * 0.001;
        STRESS_STATE.memoryMB = (agentMemory + tickBufferMemory + 15).toFixed(0);
    }
    if (DOM.metricMemory) {
        DOM.metricMemory.textContent = STRESS_STATE.memoryMB;
    }

    // Queue size
    if (DOM.metricQueueSize) {
        DOM.metricQueueSize.textContent = STRESS_STATE.queueSize.toLocaleString();
    }

    // Total ticks
    if (DOM.metricTotalTicks) {
        DOM.metricTotalTicks.textContent = totalTicks.toLocaleString();
    }

    // Throttled chart update
    updateChartsThrottled();
}

function updateMetricElement(el, value, unit) {
    if (!el) return;
    el.textContent = value;
}

function updateMiniGauge(el, pct, color) {
    if (!el) return;
    el.style.width = pct + '%';
    el.style.backgroundColor = color;
}

function calculateFPS() {
    if (STRESS_STATE.tickTimestamps.length < 2) return 0;
    const recent = STRESS_STATE.tickTimestamps.slice(-10);
    if (recent.length < 2) return 0;
    const elapsed = recent[recent.length - 1] - recent[0];
    if (elapsed <= 0) return 0;
    return ((recent.length - 1) / elapsed) * 1000;
}

function percentile(sorted, p) {
    const idx = Math.ceil(p * (sorted.length - 1));
    return sorted[idx] || 0;
}

function getTickTimeColor(ms) {
    if (ms < 100) return 'var(--success)';
    if (ms < 500) return 'var(--warning)';
    return '#e74c3c';
}

function getFpsColor(fps) {
    if (fps >= 30) return 'var(--success)';
    if (fps >= 15) return 'var(--warning)';
    return '#e74c3c';
}

// ============================================================
// WebSocket Connections
// ============================================================
function connectWebSockets() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

    // Simulation WS
    const wsSimUrl = `${wsProtocol}//${window.location.host}/ws/simulation`;
    STRESS_STATE.wsSim = new SimulationWSClient(wsSimUrl, handleWsSimMessage);
    STRESS_STATE.wsSim.connect();

    // GPU WS (for memory/queue metrics if available)
    const wsGpuUrl = `${wsProtocol}//${window.location.host}/ws/gpu`;
    STRESS_STATE.wsGpu = new SimulationWSClient(wsGpuUrl, handleWsGpuMessage);
    STRESS_STATE.wsGpu.connect();
}

function handleWsSimMessage(data) {
    // Update WS chip
    STRESS_STATE.wsSimConnected = true;
    setWsChip(DOM.wsSimChip, true);

    // Extract simulation data
    const simData = data.data || data;
    const agents = data.agents || [];

    // Update status
    updateStatus(simData.status || STRESS_STATE.statusText);

    const now = performance.now();
    const tickNum = simData.tick || STRESS_STATE.totalTicks;

    // Tick time calculation
    if (STRESS_STATE._lastSimTimestamp) {
        const tickTime = now - STRESS_STATE._lastSimTimestamp;
        STRESS_STATE.tickTimes.push(tickTime);
        // Keep rolling window of 100
        if (STRESS_STATE.tickTimes.length > 100) {
            STRESS_STATE.tickTimes.shift();
        }

        // Chart data for tick time
        STRESS_STATE.chartTickLabels.push(tickNum);
        STRESS_STATE.chartTickValues.push(parseFloat(tickTime.toFixed(2)));
        // Keep last 100
        if (STRESS_STATE.chartTickLabels.length > 100) {
            STRESS_STATE.chartTickLabels.shift();
            STRESS_STATE.chartTickValues.shift();
        }
    }
    STRESS_STATE._lastSimTimestamp = now;

    // Population from agents array
    const agentCount = agents.length || STRESS_STATE.activeAgents || 0;
    STRESS_STATE.activeAgents = agentCount;

    // Chart data for population (throttled to reduce chart labels)
    if (STRESS_STATE.totalTicks % 3 === 0) {
        STRESS_STATE.chartPopLabels.push(tickNum);
        STRESS_STATE.chartPopValues.push(agentCount);
        if (STRESS_STATE.chartPopLabels.length > 100) {
            STRESS_STATE.chartPopLabels.shift();
            STRESS_STATE.chartPopValues.shift();
        }
    }

    // Birth/death rate tracking - simulate from agent count change or extract from payload
    // The backend may include birth_count / death_count in the payload
    const births = simData.birth_count || simData.births || 0;
    const deaths = simData.death_count || simData.deaths || 0;
    if (births) STRESS_STATE.cumBirths += births;
    if (deaths) STRESS_STATE.cumDeaths += deaths;

    // Births vs Deaths bar chart (per 10-tick window)
    STRESS_STATE.currentBDBirths += births;
    STRESS_STATE.currentBDDeaths += deaths;
    if (STRESS_STATE.totalTicks % 10 === 0 && STRESS_STATE.totalTicks > 0) {
        STRESS_STATE.chartBDWindowLabels.push(`T${tickNum}`);
        STRESS_STATE.chartBDBirths.push(STRESS_STATE.currentBDBirths);
        STRESS_STATE.chartBDDeaths.push(STRESS_STATE.currentBDDeaths);
        // Keep last 20 windows
        if (STRESS_STATE.chartBDWindowLabels.length > 20) {
            STRESS_STATE.chartBDWindowLabels.shift();
            STRESS_STATE.chartBDBirths.shift();
            STRESS_STATE.chartBDDeaths.shift();
        }
        STRESS_STATE.currentBDBirths = 0;
        STRESS_STATE.currentBDDeaths = 0;
    }

    // Queue size estimate
    STRESS_STATE.queueSize = simData.queue_size || simData.pending_writes || 0;

    // Tick counter
    STRESS_STATE.totalTicks = tickNum;

    // Render agents on canvas
    if (agents.length > 0 && STRESS_STATE.agentOverlay && STRESS_STATE.canvasWidth && STRESS_STATE.canvasHeight) {
        // For large simulations, limit rendering to avoid browser freeze
        const renderAgents = agents.length > 20000 ? agents.slice(0, 20000) : agents;
        renderAgents(STRESS_STATE.agentOverlay, renderAgents, STRESS_STATE.canvasWidth, STRESS_STATE.canvasHeight);
    }

    // Update metrics UI every tick
    updateMetrics();
}

function handleWsGpuMessage(data) {
    STRESS_STATE.wsGpuConnected = true;
    setWsChip(DOM.wsGpuChip, true);

    // Extract GPU / memory metrics if available
    if (data.gpu_memory) {
        STRESS_STATE.memoryMB = (data.gpu_memory.used_mb || STRESS_STATE.memoryMB).toFixed(0);
    }
    if (data.queue_size != null) {
        STRESS_STATE.queueSize = data.queue_size;
    }
}

function setWsChip(el, connected) {
    if (!el) return;
    el.className = `ws-chip ${connected ? 'connected' : 'disconnected'}`;
}

// ============================================================
// Start / Stop Stress Test
// ============================================================
async function startStressTest() {
    if (STRESS_STATE.running) return;

    const gw = STRESS_STATE.gridWidth;
    const gh = STRESS_STATE.gridHeight;
    const maxAgents = STRESS_STATE.agentCount;

    // Update canvas size to match selected grid
    STRESS_STATE.canvasWidth = gw;
    STRESS_STATE.canvasHeight = gh;
    renderTerrain();

    // Configure via API
    try {
        await fetch('/api/simulation/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                grid_width: gw,
                grid_height: gh,
                max_agents: maxAgents
            })
        });
    } catch (e) {
        console.error('[Stress] Failed to set config:', e);
    }

    // Start simulation
    try {
        await fetch('/api/simulation/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                grid_width: gw,
                grid_height: gh,
                max_agents: maxAgents,
                stress_test: true
            })
        });
    } catch (e) {
        console.error('[Stress] Failed to start simulation:', e);
    }

    // Reset metrics
    STRESS_STATE.running = true;
    STRESS_STATE.statusText = 'running';
    STRESS_STATE.tickTimes = [];
    STRESS_STATE.tickTimestamps = [];
    STRESS_STATE.totalTicks = 0;
    STRESS_STATE.startTime = Date.now();
    STRESS_STATE.cumBirths = 0;
    STRESS_STATE.cumDeaths = 0;
    STRESS_STATE.currentBDBirths = 0;
    STRESS_STATE.currentBDDeaths = 0;
    STRESS_STATE.activeAgents = 0;
    STRESS_STATE.chartTickLabels = [];
    STRESS_STATE.chartTickValues = [];
    STRESS_STATE.chartPopLabels = [];
    STRESS_STATE.chartPopValues = [];
    STRESS_STATE.chartBDWindowLabels = [];
    STRESS_STATE.chartBDBirths = [];
    STRESS_STATE.chartBDDeaths = [];
    STRESS_STATE._lastSimTimestamp = null;

    // UI updates
    if (DOM.startBtn) DOM.startBtn.disabled = true;
    if (DOM.stopBtn) DOM.stopBtn.disabled = false;
    if (DOM.agentSlider) DOM.agentSlider.disabled = true;

    updateStatus('running');

    // Elapsed timer
    STRESS_STATE.elapsedTimer = setInterval(updateElapsed, 1000);
}

async function stopStressTest() {
    if (!STRESS_STATE.running) return;

    try {
        await fetch('/api/simulation/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
    } catch (e) {
        console.error('[Stress] Failed to stop simulation:', e);
    }

    STRESS_STATE.running = false;
    STRESS_STATE.statusText = 'stopped';

    // UI updates
    if (DOM.startBtn) DOM.startBtn.disabled = false;
    if (DOM.stopBtn) DOM.stopBtn.disabled = true;
    if (DOM.agentSlider) DOM.agentSlider.disabled = false;

    updateStatus('stopped');

    // Clear elapsed timer
    if (STRESS_STATE.elapsedTimer) {
        clearInterval(STRESS_STATE.elapsedTimer);
        STRESS_STATE.elapsedTimer = null;
    }
}

function updateStatus(status) {
    STRESS_STATE.statusText = status;
    if (!DOM.statusEl) return;

    DOM.statusEl.className = `stress-status ${status}`;
    DOM.statusEl.textContent = status.charAt(0).toUpperCase() + status.slice(1);

    // Update button states
    if (status === 'running') {
        if (DOM.startBtn) DOM.startBtn.disabled = true;
        if (DOM.stopBtn) DOM.stopBtn.disabled = false;
        if (DOM.agentSlider) DOM.agentSlider.disabled = true;
    } else if (status === 'stopped') {
        if (DOM.startBtn) DOM.startBtn.disabled = false;
        if (DOM.stopBtn) DOM.stopBtn.disabled = true;
        if (DOM.agentSlider) DOM.agentSlider.disabled = false;
    } else if (status === 'paused') {
        if (DOM.startBtn) DOM.startBtn.disabled = false;
        if (DOM.stopBtn) DOM.stopBtn.disabled = false;
    }
}

function updateElapsed() {
    if (!STRESS_STATE.startTime) return;
    const elapsed = Math.floor((Date.now() - STRESS_STATE.startTime) / 1000);
    const mins = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const secs = (elapsed % 60).toString().padStart(2, '0');
    if (DOM.metricElapsed) {
        DOM.metricElapsed.textContent = `${mins}:${secs}`;
    }
}

// ============================================================
// WS Disconnect Handling
// ============================================================
// The SimulationWSClient handles reconnect automatically,
// but we update the chips on disconnect events.
// We override onclose to update chip:
const originalConnect = SimulationWSClient.prototype.connect.bind({});

// Patch WS clients to update chips on disconnect
// We add a callback on the existing ws-client:
// Since ws-client already has reconnect, we add a periodic check
setInterval(() => {
    if (STRESS_STATE.wsSim) {
        const simConnected = STRESS_STATE.wsSim.isConnected;
        STRESS_STATE.wsSimConnected = simConnected;
        setWsChip(DOM.wsSimChip, simConnected);
    }
    if (STRESS_STATE.wsGpu) {
        const gpuConnected = STRESS_STATE.wsGpu.isConnected;
        STRESS_STATE.wsGpuConnected = gpuConnected;
        setWsChip(DOM.wsGpuChip, gpuConnected);
    }
}, 3000);
