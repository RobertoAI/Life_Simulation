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
from backend.api.simulation_api import router as simulation_router, init_router, set_session_manager
from backend.api.gpu import router as gpu_router, init_gpu_router
from backend.api.sessions_api import router as sessions_router, init_sessions_router
from backend.api.interact_ws import websocket_endpoint_interact
from backend.websocket.simulation_ws import websocket_endpoint_simulation
from backend.websocket.gpu_ws import websocket_endpoint_gpu
from backend.gpu_monitor import create_gpu_monitor
from backend.sessions import create_session_manager, SessionManager


# Backwards-compatible global reference (mirrors session_manager.get_session("main"))
engine: SimulationEngine | None = None
gpu_monitor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database, simulation engine, session manager, and GPU monitor."""
    global engine, gpu_monitor

    # Initialize database
    db_path = Settings.db_path
    if not os.path.isabs(db_path):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(project_root, db_path)

    init_db(db_path)

    # Initialize session manager and create default "main" session
    session_manager = create_session_manager()
    session_manager.create_default_session(Settings)
    app.state.session_manager = session_manager

    # Backwards-compatible reference
    engine = session_manager.get_session("main")

    # Initialize GPU monitor
    gpu_monitor = create_gpu_monitor(interval=Settings.gpu_monitor_interval)
    gpu_monitor.start()
    app.state.gpu_monitor = gpu_monitor

    # Initialize router references
    init_router(engine, Settings)
    init_gpu_router(gpu_monitor)
    set_session_manager(session_manager)
    init_sessions_router(session_manager)

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
app.include_router(sessions_router)


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


@app.websocket("/ws/interact/{session_id}")
async def websocket_interact_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time user interactions with a session."""
    sm: SessionManager | None = getattr(app.state, "session_manager", None)
    if sm is None:
        await websocket.close(code=1011, reason="Session manager not ready")
        return
    await websocket_endpoint_interact(websocket, session_id, sm)


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


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page for simulation configuration."""
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "settings": Settings.to_dict()},
    )


@app.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    """Agent cards page."""
    return templates.TemplateResponse(
        "agents.html",
        {"request": request},
    )


@app.get("/gpu", response_class=HTMLResponse)
async def gpu_page(request: Request):
    """GPU monitoring dashboard."""
    return templates.TemplateResponse(
        "gpu.html",
        {"request": request},
    )


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Analytics and metrics dashboard."""
    return templates.TemplateResponse(
        "analytics.html",
        {"request": request},
    )


@app.get("/stress-test", response_class=HTMLResponse)
async def stress_test_page(request: Request):
    """Stress test page."""
    return templates.TemplateResponse(
        "stress_test.html",
        {"request": request, "settings": Settings.to_dict()},
    )
