/**
 * canvas-utils.js - High-performance canvas rendering
 * Uses ImageData for per-pixel manipulation instead of drawRect.
 */

// Terrain type to RGBA color mapping
const TERRAIN_COLORS = [
    [26, 58, 92, 255],      // 0: water
    [74, 124, 63, 255],     // 1: plains
    [45, 90, 30, 255],      // 2: forest
    [139, 125, 107, 255],   // 3: mountain
    [212, 164, 86, 255],    // 4: desert
];

/**
 * Render a terrain map onto a canvas using ImageData.
 *
 * @param {HTMLCanvasElement} canvas - The target canvas element.
 * @param {number[][]} terrainData - 2D array of terrain type integers.
 * @param {number} width - Grid width.
 * @param {number} height - Grid height.
 */
function renderTerrainMap(canvas, terrainData, width, height) {
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    const imageData = ctx.createImageData(width, height);
    const data = imageData.data;

    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            const terrainType = terrainData[y][x];
            const color = TERRAIN_COLORS[terrainType] || [0, 0, 0, 255];
            const idx = (y * width + x) * 4;
            data[idx] = color[0];
            data[idx + 1] = color[1];
            data[idx + 2] = color[2];
            data[idx + 3] = color[3];
        }
    }

    ctx.putImageData(imageData, 0, 0);
}

/**
 * Render a resource heatmap onto a canvas using ImageData.
 * Colors: 0 = blue, 0.5 = green, 1.0 = red.
 *
 * @param {HTMLCanvasElement} canvas - The target canvas element.
 * @param {number[][]} resourceData - 2D array of resource values (0-1).
 * @param {number} width - Grid width.
 * @param {number} height - Grid height.
 */
function renderHeatmap(canvas, resourceData, width, height) {
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    const imageData = ctx.createImageData(width, height);
    const data = imageData.data;

    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            const val = resourceData[y][x];
            const [r, g, b] = heatColor(val);
            const idx = (y * width + x) * 4;
            data[idx] = r;
            data[idx + 1] = g;
            data[idx + 2] = b;
            data[idx + 3] = 255;  // alpha
        }
    }

    ctx.putImageData(imageData, 0, 0);
}

/**
 * Convert a value (0-1) to a gradient color: blue -> green -> red.
 *
 * @param {number} val - The value between 0 and 1.
 * @returns {number[]} Array of [r, g, b] values.
 */
function heatColor(val) {
    val = Math.max(0, Math.min(1, val));
    if (val < 0.5) {
        // Blue to green
        const t = val * 2;  // 0..1
        const b = Math.round(255 * (1 - t));
        const g = Math.round(255 * t);
        return [0, g, b];
    } else {
        // Green to red
        const t = (val - 0.5) * 2;  // 0..1
        const r = Math.round(255 * t);
        const g = Math.round(255 * (1 - t));
        return [r, g, 0];
   }
}

/**
 * Compute dot radius for an agent based on genome_size.
 * Returns radius in pixels (1 = 3x3 dot, 2 = 5x5 dot, etc.)
 *
 * @param {Object} agent - Agent object (may have genome_size or genome).
 * @returns {number} Dot radius (1-2).
 */
function getAgentDotRadius(agent) {
    if (agent.genome_size !== undefined) {
        // Map genome_size to radius: 0->1, 100->2
        return Math.max(1, Math.min(2, 1 + agent.genome_size / 100));
    }
    // If genome object exists, compute average
    if (agent.genome && typeof agent.genome === 'object') {
        const values = Object.values(agent.genome).filter(v => typeof v === 'number');
        if (values.length > 0) {
            const avg = values.reduce((a, b) => a + b, 0) / values.length;
            return Math.max(1, Math.min(2, 1 + avg / 100));
        }
    }
    return 1;  // default
}

/**
 * Compute color for an agent based on energy + personality hue shift.
 *
 * @param {Object} agent - Agent object with energy and optionally personality.
 * @returns {{r: number, g: number, b: number}} RGB color.
 */
function getAgentColor(agent) {
    const energy = Math.max(0, Math.min(1, agent.energy || 0));
    let r, g, b;

    if (energy >= 0.5) {
        // Yellow (0.5) to green (1.0)
        const t = (energy - 0.5) * 2;  // 0..1
        r = Math.round(200 * (1 - t));
        g = 200 + Math.round(55 * t);
        b = 0;
    } else {
        // Red (0) to yellow (0.5)
        const t = energy * 2;  // 0..1
        r = 200;
        g = Math.round(200 * t);
        b = 0;
    }

    // Personality hue shift: neuroticism adds purple tint
    if (agent.personality && typeof agent.personality === 'object') {
        const neuro = agent.personality.neuroticism || 0;
        const neuroNorm = Math.max(0, Math.min(1, neuro));
        // Blend toward purple (add blue, slightly reduce red)
        b = Math.round(Math.min(255, b + neuroNorm * 80));
        r = Math.round(r * (1 - neuroNorm * 0.15));

        // Openness adds slight cyan tint
        const openness = agent.personality.openness || 0;
        const openNorm = Math.max(0, Math.min(1, openness));
        b = Math.round(Math.min(255, b + openNorm * 40));
        g = Math.round(Math.min(255, g + openNorm * 30));
    }

    return { r, g, b };
}

/**
 * Render agents as colored dots on a canvas using ImageData.
 * Agent color is based on energy: green (high) -> yellow (medium) -> red (low).
 * Dot size scales with genome_size (if available).
 * Color hue shifts based on personality traits (e.g. neuroticism = purple tint).
 * Optional extra data is passed per-agent: genome_size, genome, personality.
 *
 * @param {HTMLCanvasElement} canvas - The target canvas element (overlay layer).
 * @param {Object[]} agents - Array of agent objects with {x, y, energy} plus optional genome/personality.
 * @param {number} mapWidth - Grid width (matches terrain width).
 * @param {number} mapHeight - Grid height (matches terrain height).
 */
function renderAgents(canvas, agents, mapWidth, mapHeight) {
    canvas.width = mapWidth;
    canvas.height = mapHeight;
    const ctx = canvas.getContext('2d');

    // Clear the overlay canvas
    ctx.clearRect(0, 0, mapWidth, mapHeight);

    const imageData = ctx.createImageData(mapWidth, mapHeight);
    const data = imageData.data;

    for (let i = 0; i < agents.length; i++) {
        const agent = agents[i];
        const ax = Math.floor(agent.x);
        const ay = Math.floor(agent.y);

        // Skip agents outside map bounds
        if (ax < 0 || ax >= mapWidth || ay < 0 || ay >= mapHeight) continue;

        const color = getAgentColor(agent);
        const dotRadius = Math.floor(getAgentDotRadius(agent));

        // Draw dot
        for (let dy = -dotRadius; dy <= dotRadius; dy++) {
            for (let dx = -dotRadius; dx <= dotRadius; dx++) {
                const px = ax + dx;
                const py = ay + dy;
                if (px >= 0 && px < mapWidth && py >= 0 && py < mapHeight) {
                    const idx = (py * mapWidth + px) * 4;
                    data[idx] = color.r;
                    data[idx + 1] = color.g;
                    data[idx + 2] = color.b;
                    data[idx + 3] = 255;
                }
            }
        }
    }

    ctx.putImageData(imageData, 0, 0);
}

/**
 * Compute generation diversity from an array of agents.
 * Returns the count of unique generation values.
 *
 * @param {Object[]} agents - Array of agent objects with optional generation field.
 * @returns {number} Number of unique generations.
 */
function getGenerationDiversity(agents) {
    if (!agents || agents.length === 0) return 0;
    const gens = new Set();
    for (const agent of agents) {
        if (agent.generation !== undefined && agent.generation !== null) {
            gens.add(agent.generation);
        }
    }
    return gens.size;
}
