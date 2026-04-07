# API Specification

Complete API documentation for the AI Life Simulator.

---

## Base URL

```
http://localhost:8000
```

All API responses are `application/json`.

---

## Simulation API

All endpoints prefixed with `/api/simulation`.

### `GET /api/simulation/status`

Returns the current simulation state.

**Request:**

No parameters.

**Response (200):**

```json
{
    "status": "running",
    "tick": 1520,
    "agent_count": 1200,
    "alive_agents": 980,
    "dead_agents": 220,
    "speed": 1.0,
    "elapsed_seconds": 45.6
}
```

#### Notes
- `status` can be: `"stopped"`, `"running"`, `"paused"`
- Returns `{"error": "Engine not initialized"}` (503) if the server hasn't started the simulation engine yet.

---

### `POST /api/simulation/start`

Starts the simulation engine. Spawns initial agents according to `Settings.initial_population`.

**Request:**

No body. Just a POST to the endpoint.

**Response (200):**

```json
{
    "success": true
}
```

**Response (503):**

```json
{
    "success": false,
    "error": "Engine not initialized"
}
```

---

### `POST /api/simulation/stop`

Stops the simulation engine. All processing halts.

**Response (200):**

```json
{
    "success": true
}
```

---

### `POST /api/simulation/pause`

Pauses the simulation. State is preserved; use `start` to resume.

**Response (200):**

```json
{
    "success": true
}
```

---

### `POST /api/simulation/speed`

Sets the simulation speed multiplier.

**Parameters:**

| Parameter | Type  | Default | Description                        |
|-----------|-------|---------|------------------------------------|
| `speed`   | float | 1.0     | Multiplier (0.5, 1.0, 2.0, 5.0, 10.0) |

**Request:**

```
POST /api/simulation/speed?speed=2.0
```

**Response (200):**

```json
{
    "success": true,
    "speed": 2.0
}
```

---

### `GET /api/simulation/map`

Returns the current terrain and resource map data for the entire world grid.

**Response (200):**

```json
{
    "width": 200,
    "height": 200,
    "terrain": [[0, 0, 1, ...], [1, 1, 0, ...], ...],
    "resources": [[0.5, 0.3, 0.0, ...], [0.1, 0.8, 0.2, ...], ...]
}
```

#### Field Descriptions

| Field      | Type             | Description                          |
|------------|------------------|--------------------------------------|
| `width`    | int              | Grid width in cells                  |
| `height`   | int              | Grid height in cells                 |
| `terrain`  | int[][]          | 2D array of terrain type IDs (0=empty, 1=grass, 2=water, etc.) |
| `resources`| float[][]        | 2D array of resource abundance (0.0–1.0) |

---

### `GET /api/simulation/agents`

Returns a paginated list of currently alive agents.

**Parameters:**

| Parameter   | Type | Default | Description                  |
|-------------|------|---------|------------------------------|
| `page`      | int  | 1       | Page number (1-indexed)      |
| `per_page`  | int  | 20      | Number of agents per page    |

**Response (200):**

```json
{
    "agents": [
        {
            "id": 1,
            "x": 42,
            "y": 17,
            "energy": 75.2,
            "age": 120,
            "genome": { ... },
            "personality": { ... },
            "alive": true
        },
        ...
    ],
    "total": 980,
    "page": 1,
    "per_page": 20,
    "pages": 49
}
```

---

### `GET /api/simulation/agents/{agent_id}`

Returns detailed information about a single agent.

**URL Parameters:**

| Parameter  | Type | Description          |
|------------|------|----------------------|
| `agent_id` | int  | Unique agent ID      |

**Response (200):**

```json
{
    "id": 42,
    "x": 42,
    "y": 17,
    "energy": 75.2,
    "age": 120,
    "genome": { "trait_a": 0.8, "trait_b": 0.3, ... },
    "personality": { "aggression": 0.6, "curiosity": 0.4, ... },
    "alive": true
}
```

**Response (404):**

```json
{
    "error": "Agent 9999 not found"
}
```

---

### `GET /api/simulation/config`

Returns the current simulation configuration settings.

**Response (200):**

```json
{
    "grid_width": 200,
    "grid_height": 200,
    "tick_interval_ms": 50,
    "ws_interval_ms": 200,
    "initial_population": 1000,
    "max_agents": 10000,
    "stress_test_agents": 50000,
    "snapshot_interval": 100,
    "gpu_monitor_interval": 1,
    "db_path": "data/simulation.db"
}
```

---

### `PUT /api/simulation/config`

Updates the configuration by accepting a JSON body with all settings.

**Request Body:**

```json
{
    "grid_width": 400,
    "grid_height": 400,
    "tick_interval_ms": 30,
    "ws_interval_ms": 150,
    "initial_population": 2000,
    "max_agents": 20000,
    "stress_test_agents": 50000,
    "snapshot_interval": 50,
    "gpu_monitor_interval": 1,
    "db_path": "data/simulation.db"
}
```

**Response (200):**

```json
{
    "success": true
}
```

**Notes:**
- All fields must be present when updating. Use `GET /api/simulation/config` first, modify, then `PUT` back.
- Some settings (like `initial_population`) only take effect on the next simulation start.

---

## GPU API

All endpoints prefixed with `/api/gpu`.

### `GET /api/gpu/current`

Returns the latest GPU metrics reading.

**Response (200):**

```json
{
    "gpu_utilization": 45.2,
    "vram_used": 2048,
    "vram_total": 8192,
    "temperature": 62,
    "power_draw": 75.5,
    "fallback": false
}
```

#### Notes
- When no NVIDIA GPU is available, `fallback` is `true` and values may be `null`.
- The fallback monitor provides simulated/approximate metrics.

---

### `GET /api/gpu/history`

Returns historical GPU readings from the in-memory ring buffer and SQLite.

**Parameters:**

| Parameter | Type | Default | Description                    |
|-----------|------|---------|--------------------------------|
| `minutes` | int  | 5       | Number of minutes of history   |

**Response (200):**

```json
{
    "fallback": false,
    "minutes": 5,
    "readings": [
        {
            "gpu_utilization": 44.1,
            "vram_used": 2048,
            "vram_total": 8192,
            "temperature": 61,
            "power_draw": 73.2,
            "timestamp": "2024-01-15T10:30:00"
        },
        ...
    ]
}
```

---

## WebSocket Endpoints

### `/ws/simulation`

Streams real-time simulation state updates.

**Connect:**

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/simulation");
```

**Message format (JSON):**

```json
{
    "type": "tick",
    "tick": 1520,
    "status": "running",
    "metrics": {
        "birth_rate": 0.05,
        "death_rate": 0.02,
        "avg_energy": 65.3,
        "avg_age": 80
    },
    "agents": [
        {"id": 1, "x": 42, "y": 17, "energy": 75, "alive": true},
        ...
    ]
}
```

#### Notes
- Agent positions are sent in batches (up to 500 agents per message) every 3 ticks to reduce bandwidth.
- Messages are broadcast at intervals defined by `Settings.ws_interval_ms`.

---

### `/ws/gpu`

Streams real-time GPU telemetry data.

**Connect:**

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/gpu");
```

**Message format (JSON):**

```json
{
    "gpu_utilization": 45.2,
    "vram_used": 2048,
    "vram_total": 8192,
    "temperature": 62,
    "power_draw": 75.5,
    "timestamp": "2024-01-15T10:30:00"
}
```

#### Notes
- Emitted at `Settings.gpu_monitor_interval` second intervals.
- Returns `null` values when GPU is unavailable (fallback mode).

---

## Page Routes

These routes serve rendered HTML pages (not REST APIs).

| Route            | Template                 | Description                 |
|------------------|--------------------------|-----------------------------|
| `GET /`          | `index.html`             | Landing / home page         |
| `GET /index`     | `index.html`             | Home page (alias)           |
| `GET /simulation`| `simulation.html`        | Live simulation canvas view  |

All templates receive the simulation config via `{{ settings }}`.

---

## Static Files

Static assets served at `/static/`:

| Path                         | Content            |
|------------------------------|--------------------|
| `/static/css/style.css`      | Global styles      |
| `/static/css/dashboard.css`  | Dashboard layout   |
| `/static/css/agent-cards.css`| Agent card grid    |
| `/static/js/simulation.js`   | Canvas rendering   |
| `/static/js/agents.js`       | Agent card logic   |
| `/static/js/analytics.js`    | Analytics dashboard|
| `/static/js/gpu-dashboard.js`| GPU monitoring UI  |
| `/static/js/ws-client.js`    | WebSocket client   |
| `/static/js/canvas-utils.js` | Canvas helpers     |

---

## Error Responses

All endpoints use consistent error formats:

| HTTP Code | Meaning              | Example Response                          |
|-----------|----------------------|-------------------------------------------|
| 200       | Success              | `{"success": true}`                       |
| 404       | Not found            | `{"error": "Agent 9999 not found"}`       |
| 503       | Service unavailable  | `{"error": "Engine not initialized"}`     |

---

## OpenAPI Auto-Docs

FastAPI auto-generates interactive API documentation:

| URL                    | Tool          |
|------------------------|---------------|
| `/docs`                | Swagger UI    |
| `/redoc`               | ReDoc         |
| `/openapi.json`        | Raw OpenAPI spec |
