"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.config import Settings
from backend.database.db import init_db
from backend.simulation.engine import SimulationEngine
from backend.api.simulation_api import router as simulation_router, init_router
from backend.api.gpu import router as gpu_router, init_gpu_router
from backend.websocket.simulation_ws import websocket_endpoint_simulation
from backend.websocket.gpu_ws import websocket_endpoint_gpu
from backend.gpu_monitor import create_gpu_monitor


# Globals
engine: SimulationEngine | None = None
gpu_monitor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database, simulation engine, and GPU monitor."""
    global engine, gpu_monitor

    # Initialize database
    db_path = Settings.db_path
    if not os.path.isabs(db_path):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(project_root, db_path)

    init_db(db_path)

    # Initialize simulation engine
    engine = SimulationEngine(Settings)

    # Initialize GPU monitor
    gpu_monitor = create_gpu_monitor(interval=Settings.gpu_monitor_interval)
    gpu_monitor.start()
    app.state.gpu_monitor = gpu_monitor

    # Initialize router references
    init_router(engine, Settings)
    init_gpu_router(gpu_monitor)

    yield  # Server is running

    # Shutdown
    if engine is not None:
        await engine.stop()
    if gpu_monitor is not None:
        await gpu_monitor.stop()


# Build the path to frontend resources relative to project root
_project_root = Path(__file__).parent.parent

app = FastAPI(
    title="AI Life Simulator",
    description="Real-time life simulation with agents, terrain, and evolution.",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
app.mount(
    "/static",
    StaticFiles(directory=str(_project_root / "frontend" / "static")),
    name="static",
)

# Setup Jinja2 templates
templates = Jinja2Templates(directory=str(_project_root / "frontend" / "templates"))

# Include API routers
app.include_router(simulation_router)
app.include_router(gpu_router)


@app.get("/ws/simulation")
async def websocket_sim_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time simulation updates."""
    if engine is None:
        await websocket.close(code=1011, reason="Engine not ready")
        return
    await websocket_endpoint_simulation(
        websocket,
        engine,
        ws_interval_ms=Settings.ws_interval_ms,
    )


@app.get("/ws/gpu")
async def websocket_gpu_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time GPU monitoring."""
    if gpu_monitor is None:
        await websocket.close(code=1011, reason="GPU monitor not ready")
        return
    await websocket_endpoint_gpu(
        websocket,
        gpu_monitor,
        config=Settings,
    )


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root page - serve index.html."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/index", response_class=HTMLResponse)
async def index_page(request: Request):
    """Index/home page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/simulation", response_class=HTMLResponse)
async def simulation_page(request: Request):
    """Simulation view page with canvas."""
    return templates.TemplateResponse(
        "simulation.html",
        {"request": request, "settings": Settings.to_dict()},
    )
