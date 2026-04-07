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
