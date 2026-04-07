// GPU Dashboard - Realtime monitoring with Chart.js

(function () {
    'use strict';

    // Config
    const MAX_POINTS = 300; // 5 minutes at 1/sec
    const WS_URL = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
                   window.location.host + '/ws/gpu';
    const RECONNECT_DELAY = 3000;

    // State
    let ws = null;
    let reconnectTimer = null;
    let chartGPU = null;
    let chartVRAM = null;
    let fallbackMode = false;

    // Utility: color based on threshold
    function indicatorColor(value, thresholds) {
        if (value >= thresholds.red) return 'red';
        if (value >= thresholds.yellow) return 'yellow';
        return 'green';
    }

    // --- Chart.js setup ---
    function initCharts() {
        const commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            plugins: {
                legend: {
                    labels: { color: '#a0a0b0', font: { size: 12 } }
                },
                tooltip: {
                    backgroundColor: '#0f3460',
                    titleColor: '#e4e4e4',
                    bodyColor: '#a0a0b0',
                    borderColor: '#1a3a5c',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    type: 'category',
                    ticks: {
                        color: '#a0a0b0',
                        maxTicksLimit: 10,
                        maxRotation: 0,
                        callback: function (_val, idx) {
                            // Only show every Nth label
                            const total = this.getLabelForValue(idx);
                            return this.tickAmount && idx % 30 === 0 ? total : '';
                        }
                    },
                    grid: { color: 'rgba(26, 58, 92, 0.3)' }
                },
                y: {
                    ticks: { color: '#a0a0b0' },
                    grid: { color: 'rgba(26, 58, 92, 0.3)' },
                    beginAtZero: true
                }
            }
        };

        // GPU Utilization Chart
        const ctxGPU = document.getElementById('gpuUtilChart');
        if (ctxGPU) {
            chartGPU = new Chart(ctxGPU, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'GPU Utilization %',
                        data: [],
                        borderColor: '#2ecc71',
                        backgroundColor: createGradient(ctxGPU, 'rgba(46, 204, 113, 0.05)', 'rgba(46, 204, 113, 0.25)'),
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHitRadius: 4
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        ...commonOptions.scales,
                        y: { ...commonOptions.scales.y, min: 0, max: 100 }
                    }
                }
            });
        }

        // VRAM Usage Chart
        const ctxVRAM = document.getElementById('vramChart');
        if (ctxVRAM) {
            chartVRAM = new Chart(ctxVRAM, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'VRAM Usage (GB)',
                        data: [],
                        borderColor: '#3498db',
                        backgroundColor: createGradient(ctxVRAM, 'rgba(52, 152, 219, 0.05)', 'rgba(52, 152, 219, 0.25)'),
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHitRadius: 4
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        ...commonOptions.scales,
                        y: { ...commonOptions.scales.y, min: 0 }
                    }
                }
            });
        }
    }

    // Create a vertical gradient for chart fill
    function createGradient(canvasEl, topColor, bottomColor) {
        const ctx = canvasEl.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, 250);
        gradient.addColorStop(0, topColor);
        gradient.addColorStop(1, bottomColor);
        return gradient;
    }

    // --- Update UI cards ---
    function updateCards(data) {
        // Fallback banner
        const bannerEl = document.getElementById('fallbackBanner');
        if (data.fallback || fallbackMode) {
            if (bannerEl) bannerEl.style.display = 'block';
            fallbackMode = true;
        } else {
            if (bannerEl) bannerEl.style.display = 'none';
        }

        // GPU Utilization
        const util = data.utilization != null ? data.utilization : 0;
        const utilEl = document.getElementById('gpuUtilValue');
        if (utilEl) {
            utilEl.textContent = util + '%';
            utilEl.className = 'card-value indicator-' + indicatorColor(util, { yellow: 50, red: 85 });
        }
        const utilBar = document.getElementById('gpuUtilBar');
        if (utilBar) {
            utilBar.style.width = util + '%';
            utilBar.className = 'gauge-fill ' + indicatorColor(util, { yellow: 50, red: 85 });
        }

        // VRAM
        const vramUsed = data.vram_used != null ? data.vram_used : 0;
        const vramTotal = data.vram_total != null ? data.vram_total : 32;
        const vramEl = document.getElementById('gpuVramValue');
        if (vramEl) vramEl.textContent = vramUsed.toFixed(1) + ' / ' + vramTotal.toFixed(1) + ' GB';
        const vramPct = vramTotal > 0 ? (vramUsed / vramTotal * 100) : 0;
        const vramBar = document.getElementById('gpuVramBar');
        if (vramBar) {
            vramBar.style.width = vramPct + '%';
            vramBar.className = 'gauge-fill ' + indicatorColor(vramPct, { yellow: 60, red: 85 });
        }

        // Temperature
        const temp = data.temperature != null ? data.temperature : 0;
        const tempEl = document.getElementById('gpuTempValue');
        if (tempEl) {
            tempEl.textContent = temp + '°C';
            tempEl.className = 'card-value indicator-' + indicatorColor(temp, { yellow: 60, red: 75 });
        }

        // Power Draw
        const power = data.power_draw;
        const powerEl = document.getElementById('gpuPowerValue');
        const powerCard = document.getElementById('powerCard');
        if (powerEl) {
            powerEl.textContent = power != null ? power + ' W' : 'N/A';
        }
        if (powerCard) {
            powerCard.style.display = power != null ? 'block' : 'none';
        }

        // GPU name strip
        const gpuNameEl = document.getElementById('gpuName');
        if (gpuNameEl && data.gpu_name) gpuNameEl.textContent = data.gpu_name;

        // Status dot
        const statusDot = document.getElementById('wsStatusDot');
        if (statusDot) {
            const c = indicatorColor(util, { yellow: 50, red: 85 });
            statusDot.className = 'pulse-dot ' + c;
        }
    }

    // Add data point to GPU utilization chart
    function addGPUDataPoint(timestamp, value) {
        if (!chartGPU) return;
        const label = formatTime(timestamp);
        chartGPU.data.labels.push(label);
        chartGPU.data.datasets[0].data.push(value);

        // Update line color based on value
        const color = indicatorColor(value, { yellow: 50, red: 85 });
        const colors = { green: '#2ecc71', yellow: '#f39c12', red: '#e74c3c' };
        chartGPU.data.datasets[0].borderColor = colors[color];
        const ctx = document.getElementById('gpuUtilChart');
        if (ctx) {
            chartGPU.data.datasets[0].backgroundColor =
                createGradient(ctx, colors[color] + '08', colors[color] + '40');
        }

        trimChart(chartGPU);
        chartGPU.update('none');
    }

    // Add data point to VRAM chart
    function addVRAMDataPoint(timestamp, value) {
        if (!chartVRAM) return;
        chartVRAM.data.labels.push(formatTime(timestamp));
        chartVRAM.data.datasets[0].data.push(value);
        trimChart(chartVRAM);
        chartVRAM.update('none');
    }

    // Trim chart data to MAX_POINTS
    function trimChart(chart) {
        while (chart.data.labels.length > MAX_POINTS) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
        }
    }

    // Format timestamp to HH:MM:SS
    function formatTime(ts) {
        const d = new Date(ts || Date.now());
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    // --- WebSocket ---
    function connectWS() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

        const wsStatusEl = document.getElementById('wsStatus');
        try {
            ws = new WebSocket(WS_URL);

            ws.onopen = function () {
                console.log('[GPU WS] Connected');
                if (wsStatusEl) {
                    wsStatusEl.textContent = 'Connected';
                    wsStatusEl.className = 'ws-status connected';
                }
                clearTimeout(reconnectTimer);
            };

            ws.onmessage = function (event) {
                try {
                    const data = JSON.parse(event.data);
                    updateCards(data);
                    const ts = data.timestamp || Date.now();
                    if (data.utilization != null) addGPUDataPoint(ts, data.utilization);
                    if (data.vram_used != null) addVRAMDataPoint(ts, data.vram_used);
                } catch (e) {
                    console.error('[GPU WS] Parse error:', e);
                }
            };

            ws.onclose = function () {
                console.log('[GPU WS] Disconnected');
                if (wsStatusEl) {
                    wsStatusEl.textContent = 'Disconnected - Reconnecting...';
                    wsStatusEl.className = 'ws-status disconnected';
                }
                reconnectTimer = setTimeout(connectWS, RECONNECT_DELAY);
            };

            ws.onerror = function () {
                console.error('[GPU WS] Error');
                ws.close();
            };
        } catch (e) {
            console.error('[GPU WS] Connection failed:', e);
            if (wsStatusEl) {
                wsStatusEl.textContent = 'Connection failed';
                wsStatusEl.className = 'ws-status disconnected';
            }
            reconnectTimer = setTimeout(connectWS, RECONNECT_DELAY);
        }
    }

    // --- Fetch initial state ---
    async function fetchInitialState() {
        try {
            const resp = await fetch('/api/gpu/current');
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            updateCards(data);

            // Pre-fill charts with any historical data if available
            if (data.history) {
                data.history.forEach(function (point) {
                    if (point.utilization != null) addGPUDataPoint(point.timestamp || Date.now(), point.utilization);
                    if (point.vram_used != null) addVRAMDataPoint(point.timestamp || Date.now(), point.vram_used);
                });
            }
        } catch (e) {
            console.warn('[GPU] Failed to fetch initial state:', e);
        }
    }

    // --- Init ---
    function init() {
        initCharts();
        fetchInitialState();
        connectWS();
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
