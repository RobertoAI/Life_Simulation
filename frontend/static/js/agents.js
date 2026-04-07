/**
 * agents.js - Agents list page logic.
 * Fetches and displays agent data with pagination, sorting, and auto-refresh.
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

    if (agents.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" style="text-align: center; padding: 2rem; color: var(--text-secondary);">
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
                <td>${agent.generation ?? '--'}</td>
                <td>${parentCell}</td>
                <td><button class="btn" style="padding: 0.25rem 0.5rem; font-size: 0.8rem;" onclick="showAgentDetail(${agent.id})">View</button></td>
            </tr>
        `;
    }).join('');
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
        const aVal = a[field];
        const bVal = b[field];
        if (aVal === undefined && bVal === undefined) return 0;
        if (aVal === undefined) return 1;
        if (bVal === undefined) return -1;
        return (aVal > bVal ? 1 : aVal < bVal ? -1 : 0) * dir;
    });
}

/**
 * Show agent detail modal.
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
            body.innerHTML = `
                <div class="detail-row">
                    <span class="detail-label">ID</span>
                    <span class="detail-value">${agent.id}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Position</span>
                    <span class="detail-value">(${formatNum(agent.x)}, ${formatNum(agent.y)})</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Energy</span>
                    <span class="detail-value" style="color: ${getEnergyColor(agent.energy)};">
                        ${agent.energy !== undefined ? (agent.energy * 100).toFixed(1) + '%' : '--'}
                    </span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Hunger</span>
                    <span class="detail-value">${agent.hunger !== undefined ? formatNum(agent.hunger) : '--'}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Health</span>
                    <span class="detail-value">${agent.health !== undefined ? (agent.health * 100).toFixed(1) + '%' : '--'}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Age</span>
                    <span class="detail-value">${formatNum(agent.age)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Generation</span>
                    <span class="detail-value">${agent.generation ?? '--'}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Parent</span>
                    <span class="detail-value">${agent.parent_id || 'None'}</span>
                </div>
                ${agent.fitness_score !== undefined ? `
                <div class="detail-row">
                    <span class="detail-label">Fitness</span>
                    <span class="detail-value">${agent.fitness_score.toFixed(3)}</span>
                </div>` : ''}
                ${agent.genome ? `
                <div class="detail-row">
                    <span class="detail-label">Genome</span>
                    <span class="detail-value" style="font-family: monospace; font-size: 0.75rem; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${agent.genome}">
                        ${agent.genome}
                    </span>
                </div>` : ''}
            `;
        }
    } catch (error) {
        console.error('Failed to load agent detail:', error);
        if (body) body.innerHTML = `<div class="error-message">Failed to load agent details: ${error.message}</div>`;
    }
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

function getStatBadge(value, label) {
    const v = clamp(value, 0, 1);
    let cls = 'stat-low';
    if (v >= 0.6) cls = 'stat-high';
    else if (v >= 0.3) cls = 'stat-medium';
    const percent = (v * 100).toFixed(0);
    return `<span class="stat-badge ${cls}">${percent}%</span>`;
}
