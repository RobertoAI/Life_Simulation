/**
 * agents.js - Agents list page logic.
 * Fetches and displays agent data with pagination, sorting, and auto-refresh.
 * Includes genome and personality visualization in detail modal.
 */

// State
let currentPage = 1;
const perPage = 20;
let totalPages = 1;
let totalCount = 0;
let agentsData = [];
let sortField = 'id';
let sortAsc = true;
let autoRefreshTimer = null;

// Named genome genes and personality traits
const GENOME_GENES = ['speed', 'metabolism', 'fertility', 'resilience', 'perception', 'aggression', 'social', 'longevity'];
const PERSONALITY_TRAITS = ['openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism'];

document.addEventListener('DOMContentLoaded', () => {
    loadAgents(currentPage);
    setupSortHeaders();
    startAutoRefresh();
    // Close modal on overlay click
    const modal = document.getElementById('agent-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeAgentModal();
        });
    }
});

/**
 * Fetch agents from the API and render the table.
 */
async function loadAgents(page) {
    currentPage = page;
    const loadingEl = document.getElementById('agents-loading');
    const tableEl = document.getElementById('agents-table');
    const tbodyEl = document.getElementById('agents-body');
    const paginationEl = document.getElementById('pagination');

    if (loadingEl) loadingEl.style.display = 'block';
    if (tableEl) tableEl.style.display = 'none';

    try {
        const response = await fetch(`/api/agents?page=${page}&per_page=${perPage}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        agentsData = data.agents || data.items || [];
        totalCount = data.total || agentsData.length;
        totalPages = data.total_pages || Math.ceil(totalCount / perPage) || 1;

        if (loadingEl) loadingEl.style.display = 'none';
        if (tableEl) tableEl.style.display = 'table';

        renderTable(agentsData);
        renderPagination();

        // Update total count badge
        const totalCountEl = document.getElementById('total-count');
        if (totalCountEl) totalCountEl.textContent = totalCount;

        // Update last refresh time
        const lastRefreshEl = document.getElementById('last-refresh');
        if (lastRefreshEl) {
            lastRefreshEl.textContent = ` | Updated: ${new Date().toLocaleTimeString()}`;
        }
    } catch (error) {
        console.error('Failed to load agents:', error);
        if (loadingEl) loadingEl.innerHTML = `
            <div class="error-message">
                Failed to load agents: ${error.message}
            </div>
        `;
    }
}

/**
 * Render table rows from agent data.
 */
function renderTable(agents) {
    const tbody = document.getElementById('agents-body');
    if (!tbody) return;

    // Count columns: 13 (added speed, metabolism, fertility)
    const colCount = 13;

    if (agents.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="${colCount}" style="text-align: center; padding: 2rem; color: var(--text-secondary);">
                    No agents found.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = agents.map((agent) => {
        const energyPercent = clamp(agent.energy, 0, 1) * 100;
        const energyColor = getEnergyColor(agent.energy);
        const healthBadge = getStatBadge(agent.health, 'Health');
        const hungerValue = agent.hunger !== undefined ? formatNum(agent.hunger) : '--';

        const parentCell = agent.parent_id
            ? `<span class="parent-link" onclick="scrollToAgent(${agent.parent_id})">${agent.parent_id}</span>`
            : `<span class="no-parent">None</span>`;

        // Genome mini-indicators for table columns
        const speedBar = agent.speed !== undefined ? genomeBarIndicator(agent.speed) : '--';
        const metabBar = agent.metabolism !== undefined ? genomeBarIndicator(agent.metabolism) : '--';
        const fertBar = agent.fertility !== undefined ? genomeBarIndicator(agent.fertility) : '--';

        return `
            <tr class="agent-row" data-agent-id="${agent.id}">
                <td class="agent-id">#${agent.id}</td>
                <td class="pos">${formatNum(agent.x)}</td>
                <td class="pos">${formatNum(agent.y)}</td>
                <td>
                    <div class="energy-bar">
                        <div class="energy-bar-fill" style="width: ${energyPercent}%; background-color: ${energyColor};"></div>
                    </div>
                    ${agent.energy !== undefined ? (agent.energy * 100).toFixed(0) + '%' : '--'}
                </td>
                <td>${hungerValue}</td>
                <td>${healthBadge}</td>
                <td>${formatNum(agent.age)}</td>
                <td>${agent.generation != null ? `<span class="gen-badge">${agent.generation}</span>` : '--'}</td>
                <td>${speedBar}</td>
                <td>${metabBar}</td>
                <td>${fertBar}</td>
                <td>${parentCell}</td>
                <td><button class="btn" style="padding: 0.25rem 0.5rem; font-size: 0.8rem;" onclick="showAgentDetail(${agent.id})">View</button></td>
            </tr>
        `;
    }).join('');
}

/**
 * Render a small colored dot + percentage for a gene value.
 */
function genomeBarIndicator(value) {
    const v = clamp(value, 0, 1);
    const pct = (v * 100).toFixed(0);
    let cls = 'low';
    if (v >= 0.6) cls = 'high';
    else if (v >= 0.3) cls = 'medium';
    return `<span class="genome-indicator"><span class="genome-dot ${cls}"></span></span> <span style="font-size:0.75rem;">${pct}%</span>`;
}

/**
 * Render pagination controls.
 */
function renderPagination() {
    const paginationEl = document.getElementById('pagination');
    if (!paginationEl) return;

    if (totalPages <= 1) {
        paginationEl.style.display = 'none';
        return;
    }

    paginationEl.style.display = 'flex';

    let html = '';

    // Previous button
    html += `<button onclick="loadAgents(${currentPage - 1})" ${currentPage <= 1 ? 'disabled' : ''}>&laquo; Prev</button>`;

    // Page numbers - show a window around current page
    const maxVisible = 7;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage + 1 < maxVisible) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }

    if (startPage > 1) {
        html += `<button onclick="loadAgents(1)">1</button>`;
        if (startPage > 2) html += `<span class="page-info">...</span>`;
    }

    for (let p = startPage; p <= endPage; p++) {
        html += `<button class="${p === currentPage ? 'active' : ''}" onclick="loadAgents(${p})">${p}</button>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) html += `<span class="page-info">...</span>`;
        html += `<button onclick="loadAgents(${totalPages})">${totalPages}</button>`;
    }

    // Next button
    html += `<button onclick="loadAgents(${currentPage + 1})" ${currentPage >= totalPages ? 'disabled' : ''}>Next &raquo;</button>`;

    // Page info
    html += `<span class="page-info">Page ${currentPage} of ${totalPages} (${totalCount} total)</span>`;

    paginationEl.innerHTML = html;
}

/**
 * Set up column sort headers.
 */
function setupSortHeaders() {
    document.querySelectorAll('.agents-table th[data-sort]').forEach((th) => {
        th.addEventListener('click', () => {
            const field = th.dataset.sort;
            if (sortField === field) {
                sortAsc = !sortAsc;
            } else {
                sortField = field;
                sortAsc = true;
            }

            // Update sort icons
            document.querySelectorAll('.agents-table th[data-sort] .sort-icon').forEach((icon) => {
                icon.textContent = '';
            });
            const icon = th.querySelector('.sort-icon');
            if (icon) {
                icon.textContent = sortAsc ? '\u25B2' : '\u25BC';
            }

            // Sort and re-render
            sortAgents();
            renderTable(agentsData);
        });
    });
}

/**
 * Sort agents data by current sort field/direction.
 */
function sortAgents() {
    const field = sortField;
    const dir = sortAsc ? 1 : -1;

    agentsData.sort((a, b) => {
        let aVal, bVal;

        // Resolve nested genome/personality fields
        if (field === 'speed' || field === 'metabolism' || field === 'fertility' || field === 'resilience' ||
            field === 'perception' || field === 'aggression' || field === 'social' || field === 'longevity') {
            // Check direct field first, then genome object
            aVal = a[field] ?? (a.genome && a.genome[field]);
            bVal = b[field] ?? (b.genome && b.genome[field]);
        } else if (PERSONALITY_TRAITS.includes(field)) {
            aVal = a[field] ?? (a.personality && a.personality[field]);
            bVal = b[field] ?? (b.personality && b.personality[field]);
        } else {
            aVal = a[field];
            bVal = b[field];
        }

        if (aVal === undefined && bVal === undefined) return 0;
        if (aVal === undefined) return 1;
        if (bVal === undefined) return -1;

        // Normalize genome/personality that may be 0-100 vs 0-1
        if (typeof aVal === 'number' && aVal > 1) aVal = aVal / 100;
        if (typeof bVal === 'number' && bVal > 1) bVal = bVal / 100;

        return (aVal > bVal ? 1 : aVal < bVal ? -1 : 0) * dir;
    });
}

/**
 * Show agent detail modal with full genome and personality bars.
 */
async function showAgentDetail(agentId) {
    const modal = document.getElementById('agent-modal');
    const title = document.getElementById('modal-title');
    const body = document.getElementById('modal-body');

    if (title) title.textContent = `Agent #${agentId}`;
    if (body) body.innerHTML = `<div class="loading-placeholder"><div class="spinner"></div></div>`;
    if (modal) modal.classList.add('active');

    try {
        // First check if we already have this agent in current page data
        let agent = agentsData.find((a) => a.id === agentId);

        // If not, fetch individual agent details
        if (!agent) {
            const response = await fetch(`/api/agents/${agentId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            agent = await response.json();
        }

        if (body && agent) {
            body.innerHTML = renderAgentDetail(agent);
        }
    } catch (error) {
        console.error('Failed to load agent detail:', error);
        if (body) body.innerHTML = `<div class="error-message">Failed to load agent details: ${error.message}</div>`;
    }
}

/**
 * Render the full agent detail HTML with genome/personality bars.
 */
function renderAgentDetail(agent) {
    const energyPct = clamp(agent.energy, 0, 1);
    const healthPct = clamp(agent.health, 0, 1);
    const hungerPct = clamp(agent.hunger, 0, 1);

    // Parse genome: can be object with named keys or flat properties
    const genome = resolveGenome(agent);
    const personality = resolvePersonality(agent);

    let html = '';

    // Basic info section
    html += `<div class="modal-section-title">Basic Info</div>`;
    html += `<div class="detail-row"><span class="detail-label">ID</span><span class="detail-value">${agent.id}</span></div>`;
    html += `<div class="detail-row"><span class="detail-label">Position</span><span class="detail-value">(${formatNum(agent.x)}, ${formatNum(agent.y)})</span></div>`;
    html += `<div class="detail-row"><span class="detail-label">Age</span><span class="detail-value">${formatNum(agent.age)}</span></div>`;
    if (agent.generation != null) {
        html += `<div class="detail-row"><span class="detail-label">Generation</span><span class="detail-value"><span class="gen-badge">${agent.generation}</span></span></div>`;
    }
    if (agent.fitness_score !== undefined) {
        html += `<div class="detail-row"><span class="detail-label">Fitness</span><span class="detail-value">${agent.fitness_score.toFixed(3)}</span></div>`;
    }

    // Parent link
    if (agent.parent_id) {
        html += `<div class="detail-row"><span class="detail-label">Parent</span><span class="detail-value"><span class="parent-link" onclick="showAgentDetail(${agent.parent_id})">Agent #${agent.parent_id}</span></span></div>`;
    } else {
        html += `<div class="detail-row"><span class="detail-label">Parent</span><span class="detail-value"><span class="no-parent">None</span></span></div>`;
    }

    // Status bars: Energy, Health, Hunger
    html += `<div class="modal-section-title">Vitals</div>`;
    html += renderStatBar('Energy', energyPct, getEnergyColor(agent.energy));
    html += renderStatBar('Health', healthPct, getHealthColor(agent.health));
    html += renderStatBar('Hunger', hungerPct, getHungerColor(agent.hunger));

    // Genome bars (8 genes)
    if (genome && Object.keys(genome).length > 0) {
        html += renderGenomeBars(genome);
    } else {
        // Show flat genome string if present (legacy)
        if (agent.genome && typeof agent.genome === 'string') {
            html += `<div class="detail-row"><span class="detail-label">Genome</span><span class="detail-value" style="font-family:monospace;font-size:0.75rem;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${agent.genome}">${agent.genome}</span></div>`;
        }
    }

    // Personality bars (5 traits)
    if (personality && Object.keys(personality).length > 0) {
        html += renderPersonalityBars(personality);
    }

    return html;
}

/**
 * Resolve genome from agent data. Returns object with named gene keys and 0-1 values.
 */
function resolveGenome(agent) {
    let genome = {};

    // Try agent.genome object
    if (agent.genome && typeof agent.genome === 'object' && !Array.isArray(agent.genome)) {
        genome = agent.genome;
    }

    // Also check direct top-level fields (flat API response)
    for (const gene of GENOME_GENES) {
        if (genome[gene] === undefined && agent[gene] !== undefined) {
            genome[gene] = agent[gene];
        }
    }

    // Normalize values to 0-1 range
    const normalized = {};
    for (const [key, val] of Object.entries(genome)) {
        if (typeof val === 'number') {
            normalized[key] = val > 1 ? val / 100 : val;
        }
    }

    return normalized;
}

/**
 * Resolve personality from agent data. Returns object with named trait keys and 0-1 values.
 */
function resolvePersonality(agent) {
    let personality = {};

    // Try agent.personality object
    if (agent.personality && typeof agent.personality === 'object' && !Array.isArray(agent.personality)) {
        personality = agent.personality;
    }

    // Also check direct top-level fields
    for (const trait of PERSONALITY_TRAITS) {
        if (personality[trait] === undefined && agent[trait] !== undefined) {
            personality[trait] = agent[trait];
        }
    }

    // Normalize values to 0-1 range
    const normalized = {};
    for (const [key, val] of Object.entries(personality)) {
        if (typeof val === 'number') {
            normalized[key] = val > 1 ? val / 100 : val;
        }
    }

    return normalized;
}

/**
 * Render a stat bar (energy/health/hunger).
 */
function renderStatBar(label, value, color) {
    const pct = (value * 100).toFixed(1);
    return `
        <div class="stat-bar-row">
            <span class="stat-bar-label">${label}</span>
            <div class="stat-bar-track">
                <div class="stat-bar-fill" style="width:${pct}%; background-color:${color};"></div>
            </div>
            <span class="stat-bar-pct">${pct}%</span>
        </div>`;
}

/**
 * Render genome horizontal bars for all 8 genes.
 */
function renderGenomeBars(genome) {
    let html = '<div class="genome-section"><h4>Genome</h4>';

    for (const gene of GENOME_GENES) {
        const val = genome[gene] !== undefined ? clamp(genome[gene], 0, 1) : null;
        if (val === null) continue;

        const pct = (val * 100).toFixed(0);
        let colorClass = 'gene-low';
        if (val >= 0.6) colorClass = 'gene-high';
        else if (val >= 0.3) colorClass = 'gene-medium';

        html += `
            <div class="gene-bar-container">
                <div class="gene-bar-label">
                    <span class="gene-name">${capitalize(gene)}</span>
                    <span class="gene-value">${pct}%</span>
                </div>
                <div class="gene-bar">
                    <div class="gene-bar-fill ${colorClass}" style="width:${pct}%;"></div>
                </div>
            </div>`;
    }

    html += '</div>';
    return html;
}

/**
 * Render personality horizontal bars for all 5 traits.
 */
function renderPersonalityBars(personality) {
    let html = '<div class="personality-section"><h4>Personality</h4>';

    for (const trait of PERSONALITY_TRAITS) {
        const val = personality[trait] !== undefined ? clamp(personality[trait], 0, 1) : null;
        if (val === null) continue;

        const pct = (val * 100).toFixed(0);
        let colorClass = 'trait-low';
        if (val >= 0.6) colorClass = 'trait-high';
        else if (val >= 0.3) colorClass = 'trait-medium';

        html += `
            <div class="trait-bar-container">
                <div class="trait-bar-label">
                    <span class="trait-name">${capitalize(trait)}</span>
                    <span class="trait-value">${pct}%</span>
                </div>
                <div class="trait-bar">
                    <div class="trait-bar-fill ${colorClass}" style="width:${pct}%;"></div>
                </div>
            </div>`;
    }

    html += '</div>';
    return html;
}

/**
 * Close agent detail modal.
 */
function closeAgentModal() {
    const modal = document.getElementById('agent-modal');
    if (modal) modal.classList.remove('active');
}

/**
 * Scroll to and highlight an agent row by ID.
 */
function scrollToAgent(agentId) {
    const row = document.querySelector(`tr.agent-row[data-agent-id="${agentId}"]`);
    if (row) {
        row.style.transition = 'background-color 0.3s';
        row.style.backgroundColor = 'var(--accent)';
        row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(() => {
            row.style.backgroundColor = '';
        }, 2000);
    } else {
        // Agent not on current page, could navigate to the right page
        // For now just show the modal
        showAgentDetail(agentId);
    }
}

/**
 * Start auto-refresh timer.
 */
function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshTimer = setInterval(() => {
        loadAgents(currentPage);
    }, 2000);
}

/**
 * Stop auto-refresh timer.
 */
function stopAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }
}

// --- Utility functions ---

function clamp(val, min, max) {
    if (val === undefined || val === null) return 0;
    return Math.max(min, Math.min(max, parseFloat(val) || 0));
}

function formatNum(val) {
    if (val === undefined || val === null) return '--';
    const num = parseFloat(val);
    if (isNaN(num)) return '--';
    return Number.isInteger(num) ? num.toString() : num.toFixed(2);
}

function getEnergyColor(energy) {
    const e = clamp(energy, 0, 1);
    if (e >= 0.6) return '#2ecc71';
    if (e >= 0.3) return '#f39c12';
    return '#e94560';
}

function getHealthColor(health) {
    const h = clamp(health, 0, 1);
    if (h >= 0.6) return '#2ecc71';
    if (h >= 0.3) return '#f39c12';
    return '#e94560';
}

function getHungerColor(hunger) {
    // For hunger, low is good (not hungry), high is bad
    const h = clamp(hunger, 0, 1);
    if (h <= 0.3) return '#2ecc71';
    if (h <= 0.6) return '#f39c12';
    return '#e94560';
}

function getStatBadge(value, label) {
    const v = clamp(value, 0, 1);
    let cls = 'stat-low';
    if (v >= 0.6) cls = 'stat-high';
    else if (v >= 0.3) cls = 'stat-medium';
    const percent = (v * 100).toFixed(0);
    return `<span class="stat-badge ${cls}">${percent}%</span>`;
}

function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}
