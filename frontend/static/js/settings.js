/**
 * Settings Page - Load, save, and export simulation configuration.
 */
class SettingsManager {
    constructor() {
        this.form = document.getElementById('settings-form');
        this.message = document.getElementById('settings-message');
        this.saveBtn = document.getElementById('save-btn');
        this.exportBtn = document.getElementById('export-btn');
        this.resetBtn = document.getElementById('reset-btn');
        this.settings = null;
        this.init();
    }

    init() {
        this.loadSettings();
        this.saveBtn.addEventListener('click', (e) => this.save(e));
        this.exportBtn.addEventListener('click', () => this.exportData());
        this.resetBtn.addEventListener('click', () => this.resetDefaults());
    }

    async loadSettings() {
        try {
            const response = await fetch('/api/simulation/config');
            if (!response.ok) throw new Error('Failed to load config');
            this.settings = await response.json();
            this.populateForm(this.settings);
        } catch (error) {
            this.showMessage('Error loading settings: ' + error.message, 'error');
        }
    }

    populateForm(data) {
        // Map config keys to form input IDs
        const mapping = {
            grid_width: 'grid_width',
            grid_height: 'grid_height',
            tick_interval_ms: 'tick_interval_ms',
            ws_interval_ms: 'ws_interval_ms',
            initial_population: 'initial_population',
            max_agents: 'max_agents',
            stress_test_agents: 'stress_test_agents',
            snapshot_interval: 'snapshot_interval',
            gpu_monitor_interval: 'gpu_monitor_interval',
            db_path: 'db_path'
        };

        for (const [key, inputId] of Object.entries(mapping)) {
            const input = document.getElementById(inputId);
            if (input && data.hasOwnProperty(key)) {
                input.value = data[key];
            }
        }
    }

    async save(e) {
        e.preventDefault();

        const config = {
            grid_width: parseInt(document.getElementById('grid_width').value),
            grid_height: parseInt(document.getElementById('grid_height').value),
            tick_interval_ms: parseInt(document.getElementById('tick_interval_ms').value),
            ws_interval_ms: parseInt(document.getElementById('ws_interval_ms').value),
            initial_population: parseInt(document.getElementById('initial_population').value),
            max_agents: parseInt(document.getElementById('max_agents').value),
            stress_test_agents: parseInt(document.getElementById('stress_test_agents').value),
            snapshot_interval: parseInt(document.getElementById('snapshot_interval').value),
            gpu_monitor_interval: parseInt(document.getElementById('gpu_monitor_interval').value),
            db_path: document.getElementById('db_path').value
        };

        this.saveBtn.disabled = true;
        this.saveBtn.textContent = 'Saving...';

        try {
            const response = await fetch('/api/simulation/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });

            const result = await response.json();

            if (result.success) {
                this.showMessage('Settings saved successfully!', 'success');
            } else {
                this.showMessage('Error: ' + (result.error || 'Unknown error'), 'error');
            }
        } catch (error) {
            this.showMessage('Error saving settings: ' + error.message, 'error');
        } finally {
            this.saveBtn.disabled = false;
            this.saveBtn.textContent = 'Save Settings';
        }
    }

    exportData() {
        const currentConfig = this.collectCurrentSettings();
        
        // Export all simulation data
        const exportData = {
            settings: currentConfig,
            exportDate: new Date().toISOString(),
            version: '0.1.0'
        };

        // Fetch agents data
        fetch('/api/simulation/agents?per_page=1000')
            .then(r => r.json())
            .then(data => {
                exportData.agents = data.agents || [];
                exportData.totalAgents = data.total || 0;
            })
            .catch(() => { exportData.agents = []; })
            .finally(() => {
                // Fetch map data
                fetch('/api/simulation/map')
                    .then(r => r.json())
                    .then(map => { exportData.map = map; })
                    .catch(() => { exportData.map = null; })
                    .finally(() => {
                        // Fetch GPU history
                        fetch('/api/gpu/history?minutes=60')
                            .then(r => r.json())
                            .then(gpu => { exportData.gpuHistory = gpu; })
                            .catch(() => { exportData.gpuHistory = null; })
                            .finally(() => {
                                // Download as JSON
                                const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                const date = new Date().toISOString().split('T')[0];
                                a.href = url;
                                a.download = `life-sim-export-${date}.json`;
                                a.click();
                                URL.revokeObjectURL(url);
                                this.showMessage('Data exported successfully!', 'success');
                            });
                    });
            });
    }

    collectCurrentSettings() {
        return {
            grid_width: parseInt(document.getElementById('grid_width').value),
            grid_height: parseInt(document.getElementById('grid_height').value),
            tick_interval_ms: parseInt(document.getElementById('tick_interval_ms').value),
            ws_interval_ms: parseInt(document.getElementById('ws_interval_ms').value),
            initial_population: parseInt(document.getElementById('initial_population').value),
            max_agents: parseInt(document.getElementById('max_agents').value),
            stress_test_agents: parseInt(document.getElementById('stress_test_agents').value),
            snapshot_interval: parseInt(document.getElementById('snapshot_interval').value),
            gpu_monitor_interval: parseInt(document.getElementById('gpu_monitor_interval').value),
            db_path: document.getElementById('db_path').value
        };
    }

    resetDefaults() {
        const defaults = {
            grid_width: 200,
            grid_height: 200,
            tick_interval_ms: 50,
            ws_interval_ms: 200,
            initial_population: 1000,
            max_agents: 10000,
            stress_test_agents: 50000,
            snapshot_interval: 100,
            gpu_monitor_interval: 1,
            db_path: 'data/simulation.db'
        };
        this.populateForm(defaults);
        this.showMessage('Defaults restored. Click Save to apply.', 'info');
    }

    showMessage(text, type = 'info') {
        this.message.textContent = text;
        this.message.style.display = 'block';
        this.message.className = 'message message-' + type;

        // Auto-hide after 5 seconds
        setTimeout(() => {
            this.message.style.display = 'none';
        }, 5000);
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new SettingsManager();
});
