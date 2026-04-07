# Performance Guide

Optimization notes, benchmark methodology, and profiling techniques for the AI Life Simulator.

---

## Benchmark Results

### Standard Configuration

| Agents  | Tick Duration | Memory    | GPU Util. | Notes              |
|---------|--------------|-----------|-----------|--------------------|
| 1,000   | 2-5ms        | ~50MB     | 30-50%    | Default config     |
| 5,000   | 5-12ms       | ~100MB    | 50-70%    | Smooth             |
| 10,000  | 15-30ms      | ~200MB    | 60-80%    | Noticeable latency  |
| 50,000  | 80-150ms     | ~500MB    | 80-95%    | Stress test        |

### WebSocket Bandwidth

| Agents  | Payload/Tick | Bandwidth  | Notes         |
|---------|-------------|------------|---------------|
| 1,000   | ~5KB        | ~25KB/s    | Negligible    |
| 5,000   | ~20KB       | ~100KB/s   | Fine on LAN   |
| 10,000  | ~40KB       | ~200KB/s   | Moderate      |
| 50,000  | ~200KB      | ~1MB/s     | Heavy         |

*Payload sizes include only agent position data sent every 3 ticks.*

### Database Performance

| Metric              | Value        | Notes                     |
|---------------------|-------------|---------------------------|
| Write latency       | 1-3ms       | SQLite WAL mode           |
| Read latency        | 0.1ms       | In-memory cache           |
| DB size (10K agents)| ~50MB       | 10 min run                |
| Queries/sec         | 10-50       | Depends on snapshot rate  |

---

## Optimization Techniques

### 1. NumPy Vectorization
Heavy grid operations (pathfinding, resource distribution) are vectorized using NumPy arrays instead of Python loops. This typically provides a 10-50x speedup for spatial computations.

**Example:** Instead of iterating over all cells:
```python
# Slow - Python loop
for x in range(width):
    for y in range(height):
        resources[x][y] *= decay_rate

# Fast - NumPy
resources *= decay_rate  # Vectorized operation
```

### 2. Batched WebSocket Updates
Instead of streaming all agent data every tick, the engine:
- Sends status + metrics **every tick** (small payload)
- Sends agent positions **every 3 ticks** (subsetted to 500 agents)
- Uses `ws_interval_ms` to throttle broadcast frequency

### 3. Engine Optimizer
The `engine_optimizer.py` module contains pre-computed lookup tables and cached calculations:
- Pre-computed neighbor offsets for spatial queries
- Cached terrain effects to avoid recomputation
- Batch updates for agent state changes

### 4. Database Write Batching
Database writes are batched to reduce I/O overhead:
- Agent snapshots written every `snapshot_interval` ticks
- GPU metrics collected in-memory, flushed periodically
- SQLite WAL mode for concurrent reads

### 5. Memory Management
- Agent data stored as flat arrays/NumPy structures where possible
- Dead agents are pruned periodically to prevent memory bloat
- WebSocket message buffer capped to prevent OOM on slow clients

---

## Benchmark Methodology

### Prerequisites
1. Clean database: `rm data/simulation.db` (or start fresh)
2. Disable other CPU-intensive processes
3. Note your hardware specs (CPU, GPU, RAM)

### Step-by-Step

**1. Single-tick latency:**
```bash
# Start simulation
curl -X POST http://localhost:8000/api/simulation/start

# Measure response time of status endpoint
time curl -s http://localhost:8000/api/simulation/status
```

**2. Sustained performance test:**
```python
import time, requests

BASE = "http://localhost:8000/api/simulation"
requests.post(f"{BASE}/start")

start = time.time()
ticks = 0
for _ in range(100):
    status = requests.get(f"{BASE}/status").json()
    if status.get("tick", 0) > ticks:
        ticks = status["tick"]
    time.sleep(0.1)

elapsed = time.time() - start
print(f"Avg tick duration: {(elapsed / ticks * 1000):.1f}ms")
```

**3. Memory profiling:**
```bash
# Requires psutil
watch -n 1 'python -c "import psutil, os; print(f\"{psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.0f} MB\")"'
```

**4. WebSocket throughput:**
Open browser dev console, connect to WebSocket, and monitor `ws-client.js` payload sizes in the Network tab.

---

## Tuning Configuration

### For Maximum Performance

```python
# backend/config.py - tuned for speed
Settings.grid_width = 100          # Smaller grid = fewer cells
Settings.grid_height = 100
Settings.tick_interval_ms = 20     # Faster ticks
Settings.ws_interval_ms = 100      # More frequent but smaller updates
Settings.max_agents = 5000         # Lower cap
Settings.snapshot_interval = 200   # Less frequent DB writes
```

### For Maximum Agent Count

```python
# backend/config.py - tuned for large populations
Settings.grid_width = 500          # Larger grid for spread
Settings.grid_height = 500
Settings.tick_interval_ms = 100    # Slower ticks to compensate
Settings.ws_interval_ms = 500      # Reduce bandwidth
Settings.max_agents = 50000        # Stress test level
Settings.snapshot_interval = 500   # Batch DB writes heavily
```

### Environment-Level Tuning

```bash
# When running in Docker
docker compose up --build \
  env GRID_WIDTH=100 \
  env MAX_AGENTS=5000 \
  env TICK_INTERVAL_MS=20
```

---

## Profiling

### CPU Profiling

```python
# Temporarily add to backend/simulation/engine.py
import cProfile
import pstats

def tick_profiled(self):
    profiler = cProfile.Profile()
    profiler.enable()

    # ... existing tick logic ...
    self._tick()

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # Top 20 functions by cumulative time
```

### Memory Profiling

```python
# pip install memory_profiler
from memory_profiler import profile

@profile
def tick(self):
    # ... existing tick logic
    pass
```

### API Response Profiling

FastAPI has profiling middleware. Add to `backend/main.py`:

```python
import time
from starlette.middleware.base import BaseHTTPMiddleware

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        print(f"{request.url.path}: {duration*1000:.2f}ms")
        return response

app.add_middleware(TimingMiddleware)
```

---

## Known Bottlenecks

| Area                | Bottleneck                | Mitigation                       |
|---------------------|--------------------------|----------------------------------|
| Large grids         | O(n²) spatial lookups    | Use spatial hashing / quadtrees  |
| Many agents         | Per-agent decision loop  | Batch decisions with NumPy       |
| WebSocket broadcast | JSON serialization       | Use MsgPack (already implemented)|
| Database writes     | fsync overhead           | Batch writes, WAL mode           |
| GPU monitor         | NVML call overhead       | Caching at interval (1s default) |

---

## Docker-Specific Optimizations

### Multi-Stage Build Benefits
- **Smaller image**: Only runtime dependencies included (~250MB vs ~800MB)
- **Security**: Non-root user, no build tools in final image
- **Build cache**: Dependencies cached in builder stage

### Health Check Tuning
```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/simulation/status')"]
  interval: 15s      # Check every 15 seconds
  timeout: 5s        # Fail after 5s
  start_period: 10s  # Grace period for startup
  retries: 3         # Restart after 3 consecutive failures
```

### Resource Limits (docker-compose.yml)
```yaml
deploy:
  resources:
    limits:
      memory: 2G
      cpus: "2.0"
    reservations:
      memory: 512M
```
