# Extending the AI Life Simulator

This guide covers how to add new agent behaviors, world types, genome traits, events, and visualization pages.

---

## Table of Contents

1. [Adding New Agent Behaviors](#adding-new-agent-behaviors)
2. [Adding Genome Traits](#adding-genome-traits)
3. [Adding World Events](#adding-world-events)
4. [Adding New World Types / Terrain](#adding-new-world-types--terrain)
5. [Adding Visualization Pages](#adding-visualization-pages)
6. [Adding API Endpoints](#adding-api-endpoints)
7. [Adding Tests](#adding-tests)

---

## Adding New Agent Behaviors

Agent behaviors are defined in `backend/simulation/decisions.py`. The decision engine selects actions based on agent state, genome, and world conditions.

### Step 1: Create a Behavior Function

Add a new behavior function that takes an `agent` and the `world` and returns a chosen action:

```python
# backend/simulation/decisions.py

def explore_behavior(agent, world):
    """Agent moves in the direction with the most unexplored territory."""
    if hasattr(agent, 'explored_count') and agent.explored_count > 100:
        return None  # Switch to another behavior

    # Find the least-explored neighboring cell
    best_cell = None
    best_score = float('inf')

    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue
            nx, ny = (agent.x + dx) % world.width, (agent.y + dy) % world.height
            visited = world.get_cell_explored(nx, ny)
            if visited < best_score:
                best_score = visited
                best_cell = (dx, dy)

    if best_cell:
        return {"action": "move", "dx": best_cell[0], "dy": best_cell[1]}

    return None
```

### Step 2: Register the Behavior

Add the behavior to the decision queue in the agent's decision loop:

```python
# Inside the decision engine in decisions.py

def make_decision(agent, world):
    """Pick the best action for an agent based on priority queue."""
    behaviors = [
        # High priority: survival behaviors
        flee_behavior,
        eat_behavior,
        # Medium priority: social behaviors
        mate_behavior,
        # Low priority: exploration
        explore_behavior,  # <-- Add your behavior here
        idle_behavior,
    ]

    for behavior_fn in behaviors:
        action = behavior_fn(agent, world)
        if action is not None:
            return action

    return {"action": "idle"}
```

### Step 3: Add Genome Influence

If you want the behavior to be influenced by genetics, add a genome weight:

```python
# backend/simulation/genome.py

GENOME_TRAITS = {
    "speed": {"default": 0.5, "mutation_rate": 0.1, "bounds": (0.0, 1.0)},
    "aggression": {"default": 0.3, "mutation_rate": 0.1, "bounds": (0.0, 1.0)},
    "exploration": {"default": 0.5, "mutation_rate": 0.1, "bounds": (0.0, 1.0)},  # <-- New trait
}
```

Then in your behavior:

```python
def explore_behavior(agent, world):
    exploration_rate = agent.genome.get("exploration", 0.5)
    # Use exploration_rate to influence behavior
    if random.random() > exploration_rate:
        return None  # Skip this behavior based on genome
    # ... proceed with exploration logic
```

---

## Adding Genome Traits

Genome traits control inherited agent properties that evolve over time.

### Step 1: Define the Trait

```python
# backend/simulation/genome.py

class Genome:
    TRAITS = {
        "speed": {"default": 0.5, "mutation_rate": 0.1, "bounds": (0.0, 1.0)},
        "aggression": {"default": 0.3, "mutation_rate": 0.1, "bounds": (0.0, 1.0)},
        "social": {"default": 0.5, "mutation_rate": 0.05, "bounds": (0.0, 1.0)},
        # Add your custom trait:
        "resilience": {"default": 0.5, "mutation_rate": 0.08, "bounds": (0.0, 1.0)},
    }
```

### Step 2: Use Trait in Agent State

```python
# backend/simulation/agent_state.py

def consume_energy(self, amount):
    """Modify energy based on resilience genome trait."""
    resilience = self.genome.get("resilience", 0.5)
    effective_cost = amount * (1.0 - resilience * 0.3)  # Resilient agents use less energy
    self.energy -= effective_cost
```

### Step 3: Display in Frontend

Add the trait to agent cards or the agent detail view in templates or JavaScript.

---

## Adding World Events

Events are global occurrences that affect all agents or the terrain.

### Step 1: Define the Event

```python
# backend/simulation/events.py

class WorldEvent:
    def __init__(self, name, trigger, effect):
        self.name = name
        self.trigger = trigger    # Callable: returns True when event should fire
        self.effect = effect      # Callable: modifies agents/world


def create_drought_event():
    """Drought reduces resources on all grass tiles."""
    def trigger(engine):
        return engine.tick > 1000 and random.random() < 0.001

    def effect(engine):
        for x in range(engine.world.width):
            for y in range(engine.world.height):
                if engine.world.terrain[x][y] == TERRAIN_GRASS:
                    engine.world.resources[x][y] *= 0.3  # Reduce resources

    return WorldEvent(
        name="Drought",
        trigger=trigger,
        effect=effect
    )
```

### Step 2: Register Events

```python
# backend/simulation/events.py

DEFAULT_EVENTS = [
    create_seasonal_change,
    create_resource_bloom,
    create_drought_event,  # <-- Add your event
    create_migration,
]
```

### Step 3: Fire Events in the Engine

The engine loop checks event triggers each tick:

```python
# backend/simulation/engine.py

def tick_events(self):
    for event in self.events:
        if event.trigger(self):
            event.effect(self)
            self.logger.info(f"Event triggered: {event.name}")
```

---

## Adding New World Types / Terrain

Terrain types are managed in `backend/simulation/world.py`.

### Step 1: Define Terrain Constants

```python
# backend/simulation/world.py

TERRAIN_TYPES = {
    T_EMPTY: {"name": "Empty", "color": (80, 80, 80)},
    T_GRASS: {"name": "Grass", "color": (50, 160, 50)},
    T_WATER: {"name": "Water", "color": (30, 100, 180)},
    T_SAND: {"name": "Sand", "color": (194, 178, 128)},
    T_FOREST: {"name": "Forest", "color": (20, 80, 30)},  # <-- New type
}
```

### Step 2: Implement Terrain Effects

```python
class World:
    def get_terrain_effect(self, x, y):
        """Returns terrain-specific modifiers."""
        terrain_type = self.terrain[x][y]
        type_info = TERRAIN_TYPES.get(terrain_type, TERRAIN_TYPES.get(T_EMPTY, {}))

        effects = {"energy_cost": 1.0, "resource_rate": 0.0}

        if type_info["name"] == "Forest":
            effects["energy_cost"] = 1.5  # Harder to move through
            effects["resource_rate"] = 0.8  # But more resources

        return effects
```

### Step 3: Map Generation

Add the new terrain to your map generation algorithm:

```python
def generate_map(self):
    # ... existing generation logic ...
    for x in range(self.width):
        for y in range(self.height):
            if noise(x, y) > 0.85:  # High altitude areas
                self.terrain[x][y] = T_FOREST
```

### Step 4: Frontend Display

Update the color palette in `canvas-utils.js` or your canvas rendering code to display the new terrain type.

---

## Adding Visualization Pages

### Step 1: Create the Template

```html
<!-- frontend/templates/dashboard.html -->
{% extends "base.html" %}

{% block title %}Custom Dashboard{% endblock %}

{% block content %}
<h1>Custom Dashboard</h1>
<div id="chart-container"></div>
<script src="/static/js/custom-dashboard.js"></script>
{% endblock %}
```

### Step 2: Add the Route

```python
# backend/main.py

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Custom dashboard page."""
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "settings": Settings.to_dict()},
    )
```

### Step 3: Create the JavaScript

```javascript
// frontend/static/js/custom-dashboard.js

class CustomDashboard {
    constructor() {
        this.ws = null;
        this.data = [];
        this.init();
    }

    init() {
        this.connectWebSocket();
        this.setupUI();
    }

    connectWebSocket() {
        this.ws = new WebSocket(`ws://${location.host}/ws/simulation`);
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.data.push(data.metrics);
            this.render();
        };
    }

    render() {
        // Chart rendering logic
        console.log("Dashboard updated with", this.data.length, "data points");
    }

    setupUI() {
        // UI initialization
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new CustomDashboard();
});
```

### Step 4: Add Navigation Link

Add a link to your new page in `frontend/templates/base.html`:

```html
<nav>
    <a href="/">Home</a>
    <a href="/simulation">Simulation</a>
    <a href="/agents">Agents</a>
    <a href="/analytics">Analytics</a>
    <a href="/gpu">GPU</a>
    <a href="/dashboard">Custom Dashboard</a>  <!-- <-- Add -->
</nav>
```

---

## Adding API Endpoints

### Step 1: Create the Route

```python
# backend/api/custom_api.py

from fastapi import APIRouter

router = APIRouter(prefix="/api/custom", tags=["Custom"])


@router.get("/population")
async def get_population_stats():
    """Return population statistics across all simulation runs."""
    # Your logic here
    return {
        "current": 1200,
        "peak": 5000,
        "average": 2300,
    }
```

### Step 2: Register the Router

```python
# backend/main.py

from backend.api.custom_api import router as custom_router

app.include_router(custom_router)
```

---

## Adding Tests

### Step 1: Create Test Module

```python
# tests/test_custom_behavior.py

import pytest
from backend.simulation.decisions import explore_behavior
from backend.simulation.world import World
from backend.simulation.agent_state import Agent


def test_explore_behavior():
    world = World(width=50, height=50)
    agent = Agent(id=1, x=25, y=25)

    action = explore_behavior(agent, world)

    assert action is not None
    assert "action" in action
    assert action["action"] == "move"
    assert "dx" in action
    assert "dy" in action
```

### Step 2: Run Tests

```bash
pytest tests/ -v
```

---

## Quick Reference: File Locations

| What to Modify            | File                                        |
|---------------------------|---------------------------------------------|
| Agent behaviors           | `backend/simulation/decisions.py`           |
| Genome traits             | `backend/simulation/genome.py`              |
| World events              | `backend/simulation/events.py`              |
| Terrain types             | `backend/simulation/world.py`               |
| Agent state/attributes    | `backend/simulation/agent_state.py`         |
| Personality model         | `backend/simulation/personality.py`         |
| Simulation engine loop    | `backend/simulation/engine.py`              |
| Configuration defaults    | `backend/config.py`                         |
| API endpoints             | `backend/api/simulation_api.py`, `backend/api/gpu.py` |
| Frontend templates        | `frontend/templates/`                       |
| Static JavaScript         | `frontend/static/js/`                       |
| Static CSS                | `frontend/static/css/`                      |
| Tests                     | `tests/`                                    |
