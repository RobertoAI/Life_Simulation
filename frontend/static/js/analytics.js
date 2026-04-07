// Analytics Dashboard - Chart.js with auto-refresh

(function () {
    'use strict';

    const REFRESH_INTERVAL = 10000; // 10 seconds
    let charts = {};
    let refreshTimer = null;

    // Common chart options
    function commonOptions(title) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 400 },
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
                    ticks: { color: '#a0a0b0', maxTicksLimit: 12, maxRotation: 0 },
                    grid: { color: 'rgba(26, 58, 92, 0.3)' }
                },
                y: {
                    ticks: { color: '#a0a0b0' },
                    grid: { color: 'rgba(26, 58, 92, 0.3)' },
                    beginAtZero: true
                }
            }
        };
    }

    function createGradient(ctxEl, top, bottom) {
        const ctx = ctxEl.getContext('2d');
        const g = ctx.createLinearGradient(0, 0, 0, 280);
        g.addColorStop(0, top);
        g.addColorStop(1, bottom);
        return g;
    }

    // --- Tab switching ---
    function initTabs() {
        document.querySelectorAll('.analytics-tab').forEach(function (tab) {
            tab.addEventListener('click', function () {
                document.querySelectorAll('.analytics-tab').forEach(function (t) { t.classList.remove('active'); });
                document.querySelectorAll('.analytics-panel').forEach(function (p) { p.classList.remove('active'); });
                this.classList.add('active');
                var panel = document.getElementById(this.getAttribute('data-panel'));
                if (panel) panel.classList.add('active');
            });
        });
    }

    // --- Chart creators ---
    function createPopulationChart() {
        var ctx = document.getElementById('populationChart');
        if (!ctx) return;
        charts.population = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Population',
                    data: [],
                    borderColor: '#e94560',
                    backgroundColor: createGradient(ctx, 'rgba(233, 69, 96, 0.05)', 'rgba(233, 69, 96, 0.2)'),
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 1,
                    pointHitRadius: 5
                }]
            },
            options: commonOptions('Population Over Time')
        });
    }

    function createBirthDeathChart() {
        var ctx = document.getElementById('birthDeathChart');
        if (!ctx) return;
        charts.birthdeath = new Chart(ctx, {
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
            options: commonOptions('Birth / Death Rates')
        });
    }

    function createDiversityChart() {
        var ctx = document.getElementById('diversityChart');
        if (!ctx) return;
        charts.diversity = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Genetic Diversity Index',
                    data: [],
                    borderColor: '#9b59b6',
                    backgroundColor: createGradient(ctx, 'rgba(155, 89, 182, 0.05)', 'rgba(155, 89, 182, 0.2)'),
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 1,
                    pointHitRadius: 5
                }]
            },
            options: commonOptions('Genetic Diversity Index')
        });
    }

    function createEventChart() {
        var ctx = document.getElementById('eventChart');
        if (!ctx) return;
        charts.events = new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: []
            },
            options: {
                ...commonOptions('Event Timeline'),
                scales: {
                    x: {
                        type: 'category',
                        labels: [],
                        ticks: { color: '#a0a0b0', maxTicksLimit: 12, maxRotation: 45 },
                        grid: { color: 'rgba(26, 58, 92, 0.3)' }
                    },
                    y: {
                        ticks: { color: '#a0a0b0' },
                        grid: { color: 'rgba(26, 58, 92, 0.3)' },
                        beginAtZero: true
                    }
                }
            }
        });
    }

    // --- Data loading ---
    async function fetchJSON(url) {
        try {
            const resp = await fetch(url);
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return await resp.json();
        } catch (e) {
            console.warn('[Analytics] Fetch error for ' + url + ':', e.message);
            return null;
        }
    }

    function showNoData(elementId) {
        var el = document.getElementById(elementId);
        if (el) {
            el.innerHTML = '<div class="no-data"><div class="icon">📊</div><p>No data yet - start the simulation to collect analytics</p></div>';
        }
    }

    function hideNoData(elementId) {
        var el = document.getElementById(elementId);
        if (el && el.classList && el.classList.contains('no-data')) {
            // Only hide if we've replaced it with a chart
        }
    }

    // --- Fetch and populate all charts ---
    async function refreshAll() {
        var data;

        // Population
        data = await fetchJSON('/api/analytics/population');
        if (charts.population) {
            if (data && data.timeline && data.timeline.length > 0) {
                charts.population.data.labels = [];
                charts.population.data.datasets[0].data = [];
                data.timeline.forEach(function (p) {
                    charts.population.data.labels.push(p.timestamp || p.label || '');
                    charts.population.data.datasets[0].data.push(p.count != null ? p.count : p.value || 0);
                });
                charts.population.update();
            } else {
                charts.population.data.labels = [];
                charts.population.data.datasets[0].data = [];
                charts.population.update();
            }
        }

        // Birth/Death
        data = await fetchJSON('/api/analytics/birthdeath');
        if (charts.birthdeath) {
            if (data && data.timeline && data.timeline.length > 0) {
                charts.birthdeath.data.labels = [];
                charts.birthdeath.data.datasets[0].data = [];
                charts.birthdeath.data.datasets[1].data = [];
                data.timeline.forEach(function (p) {
                    charts.birthdeath.data.labels.push(p.timestamp || p.label || '');
                    charts.birthdeath.data.datasets[0].data.push(p.births || 0);
                    charts.birthdeath.data.datasets[1].data.push(p.deaths || 0);
                });
                charts.birthdeath.update();
            } else {
                charts.birthdeath.data.labels = [];
                charts.birthdeath.data.datasets[0].data = [];
                charts.birthdeath.data.datasets[1].data = [];
                charts.birthdeath.update();
            }
        }

        // Diversity
        data = await fetchJSON('/api/analytics/diversity');
        if (charts.diversity) {
            if (data && data.timeline && data.timeline.length > 0) {
                charts.diversity.data.labels = [];
                charts.diversity.data.datasets[0].data = [];
                data.timeline.forEach(function (p) {
                    charts.diversity.data.labels.push(p.timestamp || p.label || '');
                    charts.diversity.data.datasets[0].data.push(p.index != null ? p.index : p.value || 0);
                });
                charts.diversity.update();
            } else {
                charts.diversity.data.labels = [];
                charts.diversity.data.datasets[0].data = [];
                charts.diversity.update();
            }
        }

        // Events
        data = await fetchJSON('/api/analytics/events');
        if (charts.events) {
            if (data && data.events && data.events.length > 0) {
                var labels = [];
                var yVals = [];
                var bgColors = [];
                data.events.forEach(function (e, idx) {
                    labels.push(e.timestamp || e.label || 'T+' + idx);
                    yVals.push(1);
                    var colors = { '#2ecc71': 'birth', '#e74c3c': 'death', '#3498db': 'event' };
                    bgColors.push('rgba(233, 69, 96, 0.7)');
                });
                charts.events.data.labels = labels;
                charts.events.data.datasets = [{
                    label: 'Events',
                    data: yVals.map(function (v, i) { return { x: labels[i], y: v }; }),
                    backgroundColor: bgColors,
                    pointRadius: 6,
                    pointHoverRadius: 9
                }];
                charts.events.update();
            } else {
                charts.events.data = { datasets: [], labels: [] };
                charts.events.update();
            }
        }
    }

    // --- Init ---
    function init() {
        initTabs();
        createPopulationChart();
        createBirthDeathChart();
        createDiversityChart();
        createEventChart();

        refreshAll();
        refreshTimer = setInterval(refreshAll, REFRESH_INTERVAL);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
