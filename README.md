# AI Life Simulator

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A real-time, GPU-accelerated life simulation with autonomous AI agents, genetic evolution, terrain dynamics, and live telemetry dashboards.

![Simulation Screenshot](docs/screenshots/simulation-placeholder.png)

---

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/RobertoAI/Life_Simulation.git && cd Life_Simulation
pip install -r requirements.txt

# 2. Run
./start.sh

# 3. Open browser → http://localhost:8000
```

Or with Docker:
```bash
docker compose up --build
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (Client)                         │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌───────────────┐    │
│  │Simulation│ │  Agents    │ │ Analytics│ │ GPU Dashboard │    │
│  │  Canvas  │ │   Cards    │ │ Dashboard│ │   & Charts    │    │
│  └────┬─────┘ └─────┬──────┘ └────┬─────┘ └──────┬────────┘    │
└───────┼─────────────┼─────────────┼──────────────┼─────────────┘
        │ HTTP REST   │ HTTP REST   │ HTTP REST    │ WebSocket
        │ + WebSocket │             │              │ real-time
┌───────┼─────────────┼─────────────┼──────────────┼─────────────┐
│                    FastAPI Server (backend/main.py)             │
│  ┌──────────────────┤ ├──────────────┤ ├──────────────────────┐ │
│  │Simulation API    │ │  GPU API     │ │   WebSocket Hub      │ │
│  │  /api/simulation/*│ │ /api/gpu/*  │ │  /ws/simulation      │ │
│  │  /api/simulation/ │ │ /api/gpu/   │ │  /ws/gpu             │ │
│  │  /config          │ │ /current    │ │                      │ │
│  │  /agents          │ │ /history    │ │                      │ │
│  └────────┬─────────┘ └──────┬───────┘ └──────────┬───────────┘ │
└───────────┼──────────────────┼────────────────────┼─────────────┘
            │                  │                    │
┌───────────┼──────────────────┼────────────────────┼─────────────┐
│           │  Simulation Engine│                    │            │
│  ┌────────▼────────┐ ┌───────▼────────┐  ┌───────▼──────────┐  │
│  │   World & Grid  │ │ Agent Manager  │  │  GPU Monitor     │  │
│  │  Terrain/Resrcs │ │ Life/Decisions │  │  NVML / fallback │  │
│  └────────┬────────┘ └───────┬────────┘  └───────┬──────────┘  │
│           │                  │                    │              │
│  ┌────────▼──────────────────▼────────────────────▼──────────┐  │
│  │                     SQLite (data/)                        │  │
│  │  agents | gpu_history | metrics                           │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
Life_Simulation/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Global Settings (pydantic-free class)
│   ├── api/
│   │   ├── simulation_api.py    # REST API: /api/simulation/*
│   │   └── gpu.py               # REST API: /api/gpu/*
│   ├── websocket/
│   │   ├── simulation_ws.py     # Real-time simulation stream
│   │   └── gpu_ws.py            # Real-time GPU telemetry
│   ├── simulation/
│   │   ├── engine.py            # Core simulation loop
│   │   ├── world.py             # Terrain + resource grid
│   │   ├── agent_state.py       # Agent data model + genome
│   │   ├── decisions.py         # Agent behavior / AI logic
│   │   ├── genome.py            # Genetic traits + mutation
│   │   ├── events.py            # World events system
│   │   ├── personality.py       # Personality traits model
│   │   ├── metrics.py           # Analytics / statistics
│   │   ├── auto_balance.py      # Dynamic difficulty balancing
│   │   └── engine_optimizer.py  # NumPy-accelerated computations
│   ├── gpu_monitor/
│   │   ├── monitor.py           # NVML-based GPU monitoring
│   │   └── fallback.py          # CPU fallback when no GPU
│   ├── database/
│   │   ├── db.py                # SQLite connection + schema
│   │   ├── models.py            # ORM-like data models
│   │   └── queries.py           # Database query helpers
│   └── utils/
│       └── logger.py            # Structured logging
├── frontend/
│   ├── templates/
│   │   ├── base.html            # Shared layout + navigation
│   │   ├── index.html           # Landing page
│   │   ├── simulation.html      # Canvas simulation view
│   │   ├── agents.html          # Agent cards grid
│   │   ├── analytics.html       # Charts & analytics
│   │   └── gpu.html             # GPU dashboard
│   └── static/
│       ├── css/                 # Stylesheets
│       └── js/                  # Client-side JavaScript
├── data/                        # SQLite database (gitignored)
├── tests/                       # Unit & integration tests
├── docs/                        # Documentation
│   ├── API.md                   # Full API specification
│   ├── EXTENDING.md             # Extension guide
│   └── PERFORMANCE.md           # Optimization & benchmarks
├── Dockerfile                   # Multi-stage Docker build
├── docker-compose.yml           # Containerized deployment
├── start.sh                     # Development run script
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

---

## Technology Stack

| Component          | Technology    | Why?                                                     |
|--------------------|---------------|----------------------------------------------------------|
| Backend Framework  | FastAPI       | Async-native, auto OpenAPI docs, excellent WS support    |
| Server             | Uvicorn       | High-performance ASGI server with ASGI-3 lifecycle       |
| Numerical Compute  | NumPy         | Vectorized grid operations, spatial queries at O(1)      |
| Database           | SQLite        | Zero-config, ACID compliant, perfect for local simulation|
| GPU Monitor        | NVML (pynvml) | Direct NVIDIA driver telemetry for utilization, VRAM, etc|
| WebSocket Protocol | MsgPack       | Binary serialization — 40-60% smaller payloads than JSON |
| Frontend           | Vanilla JS    | Zero build step, Canvas API for rendering               |
| Templating         | Jinja2        | Server-side HTML rendering with FastAPI integration      |
| Logging            | Structlog     | Structured, JSON-capable log output for debugging        |
| Containerization   | Docker        | Reproducible deployments, multi-stage builds             |

---

## API Documentation

### Base URL
```
http://localhost:8000
```

### Simulation Endpoints (`/api/simulation`)

| Method | Path                  | Description                        | Parameters                          |
|--------|-----------------------|------------------------------------|-------------------------------------|
| GET    | `/api/simulation/status`    | Current simulation state           | None                                |
| POST   | `/api/simulation/start`     | Start the simulation               | None                                |
| POST   | `/api/simulation/stop`      | Stop the simulation                | None                                |
| POST   | `/api/simulation/pause`     | Pause the simulation               | None                                |
| POST   | `/api/simulation/speed`     | Set speed multiplier               | `speed` (float, default 1.0)        |
| GET    | `/api/simulation/map`       | Terrain + resource grid data       | None                                |
| GET    | `/api/simulation/agents`    | Paginated agent list               | `page` (int, default 1), `per_page` (int, default 20) |
| GET    | `/api/simulation/agents/{agent_id}` | Single agent details     | `agent_id` (path int)               |
| GET    | `/api/simulation/config`    | Current simulation config          | None                                |
| PUT    | `/api/simulation/config`    | Update simulation config           | JSON body with settings             |

### GPU Endpoints (`/api/gpu`)

| Method | Path            | Description                     | Parameters                    |
|--------|-----------------|---------------------------------|-------------------------------|
| GET    | `/api/gpu/current`   | Latest GPU metrics              | None                          |
| GET    | `/api/gpu/history`   | Historical GPU readings         | `minutes` (int, default 5)    |

### Page Routes

| Path              | Description              |
|-------------------|--------------------------|
| `/`               | Home / Landing page      |
| `/index`          | Index page               |
| `/simulation`     | Live simulation canvas   |

### WebSocket Endpoints

| Endpoint              | Protocol  | Description                          | Payload                         |
|-----------------------|-----------|--------------------------------------|---------------------------------|
| `/ws/simulation`      | WebSocket | Real-time simulation state stream    | JSON: `{status, tick, metrics, agents[]}` |
| `/ws/gpu`             | WebSocket | Real-time GPU telemetry stream       | JSON: `{gpu_util, vram_used, temperature, power_draw}` |

WebSocket messages are MsgPack-encoded for performance. Connect with:
```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/simulation`);
ws.binaryType = 'arraybuffer';  // for MsgPack
ws.onmessage = (e) => {
    const data = e.data;  // decode with msgpack.unpack
};
```

---

## Configuration

All settings live in `backend/config.py`. The `Settings` class provides defaults and a `to_dict()` method for API serialization.

| Setting                  | Default  | Description                           |
|--------------------------|----------|---------------------------------------|
| `grid_width`             | 200      | World grid width in cells             |
| `grid_height`            | 200      | World grid height in cells            |
| `tick_interval_ms`       | 50       | Milliseconds per simulation tick      |
| `ws_interval_ms`         | 200      | WebSocket broadcast interval          |
| `initial_population`     | 1000     | Starting agent count                  |
| `max_agents`             | 10000    | Hard agent cap                        |
| `stress_test_agents`     | 50000    | Max agents for stress testing         |
| `snapshot_interval`      | 100      | Ticks between state snapshots         |
| `gpu_monitor_interval`   | 1        | Seconds between GPU readings          |
| `db_path`                | data/simulation.db | SQLite database path        |

### Environment Variables

Override settings via environment variables when running with Docker or `.env`:

```bash
GRID_WIDTH=400
GRID_HEIGHT=400
INITIAL_POPULATION=2000
MAX_AGENTS=20000
```

---

## GPU Monitoring Setup

The GPU monitor uses NVIDIA's NVML library by default and falls back to a CPU-based monitor when no GPU is available.

### Requirements
- NVIDIA GPU with driver installed
- `nvidia-ml-py` Python package (installed via requirements)

### Check GPU Status
```bash
curl http://localhost:8000/api/gpu/current
# Response includes "fallback": true if monitoring via software fallback
```

### Live GPU Dashboard
Open `http://localhost:8000/gpu` for real-time charts showing:
- GPU utilization (%)
- VRAM usage
- Temperature (°C)
- Power draw (W)

### Disabling GPU Monitor
The fallback automatically activates when no NVIDIA GPU is detected. No configuration needed.

---

## Stress Testing

To test the simulation engine at scale:

```bash
# Set high agent count
curl -X PUT http://localhost:8000/api/simulation/config \
  -H "Content-Type: application/json" \
  -d '{"initial_population": 10000, "max_agents": 50000}'

# Start simulation
curl -X POST http://localhost:8000/api/simulation/start

# Monitor performance via metrics endpoint
curl http://localhost:8000/api/simulation/status
```

**Expected performance** on modern hardware:

| Agents  | Tick Rate    | Memory    | Notes                    |
|---------|-------------|-----------|--------------------------|
| 1,000   | 50ms        | ~50MB     | Default config           |
| 5,000   | 50ms        | ~100MB    | Smooth                   |
| 10,000  | 50-80ms     | ~200MB    | Noticeable on older CPUs |
| 50,000  | 100-200ms   | ~500MB    | Stress test territory    |

See `docs/PERFORMANCE.md` for detailed benchmark methodology.

---

## Docker Deployment

### Quick Start
```bash
docker compose up --build -d
```

### Manual Build
```bash
docker build -t life-simulation .
docker run -p 8000:8000 -v $(pwd)/data:/app/data life-simulation
```

### Docker Compose Features
- **Named volumes** for database persistence
- **Environment variables** for configuration
- **Health checks** via `/api/simulation/status`
- **Auto-restart** on failure
- **Non-root user** inside container for security

### GPU in Docker
For GPU passthrough with NVIDIA Container Toolkit:
```yaml
# Add to docker-compose.yml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

---

## Extension Guide

### Adding New Agent Behaviors
1. Create a new module in `backend/simulation/behaviors/`
2. Implement a class that takes `agent` + `world` and returns an action
3. Register in `backend/simulation/decisions.py`

### Adding Genome Traits
1. Add new fields to the `Genome` class in `backend/simulation/genome.py`
2. Update the mutation logic to include the new trait
3. Modify `decisions.py` to factor the trait into agent behavior

### Adding World Events
1. Define the event in `backend/simulation/events.py`
2. Add trigger conditions (time-based, population-based, random)
3. Implement the effect callback that modifies agents or terrain

### Adding Visualization Pages
1. Create HTML template in `frontend/templates/`
2. Add a `@app.get()` route in `backend/main.py`
3. Create CSS in `frontend/static/css/` and JS in `frontend/static/js/`

See `docs/EXTENDING.md` for code examples.

---

## Troubleshooting

| Problem                          | Solution                                              |
|----------------------------------|-------------------------------------------------------|
| Port 8000 already in use         | Run `./start.sh --port 8001` or kill existing process |
| `ModuleNotFoundError`            | Run `pip install -r requirements.txt`                 |
| No GPU detected                  | Fallback activates automatically; no action needed    |
| SQLite locked                    | Close other processes accessing `data/simulation.db`  |
| WebSocket disconnects            | Check browser console for errors; verify server is running |
| Agents not spawning              | Check `Settings.initial_population` > 0 and call `/api/simulation/start` |
| Slow performance                 | Reduce `grid_width`/`grid_height`, set `--no-gpu` flag |
| Docker health check failing      | Wait 15s for startup; check logs: `docker compose logs` |

---

## Performance Benchmarks

| Metric                   | Default (1K agents) | 10K Agents | 50K (Stress) |
|--------------------------|---------------------|------------|--------------|
| Tick duration            | 2-5ms               | 15-30ms    | 80-150ms     |
| Memory usage             | ~50MB               | ~200MB     | ~500MB       |
| WebSocket payload        | ~5KB                | ~40KB      | ~200KB       |
| GPU utilization (if avail) | 30-50%            | 60-80%     | 80-95%       |
| DB writes/sec            | 10                  | 50         | 200          |

**Test environment:** NVIDIA RTX 4060, 16GB RAM, Python 3.12, Linux.
See `docs/PERFORMANCE.md` for methodology and optimization notes.

---

## License

MIT License. See LICENSE file for details.
