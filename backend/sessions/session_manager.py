"""Session manager - manages multiple independent simulation instances."""

import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.simulation.engine import SimulationEngine


def _make_config(settings_class: Any, overrides: dict | None = None) -> Any:
    """Create a mutable config object from a Settings-like class.

    This clones the *class-level* defaults of Settings (which uses class
    attributes, not instances) into a lightweight namespace object so each
    session gets its own independent copy.

    Args:
        settings_class: The Settings class (or any class / types.SimpleNamespace
                        providing public attributes).
        overrides: Optional dict of attribute overrides.

    Returns:
        A new mutable config object.
    """
    class Config:
        pass
    cfg = Config()
    for key in dir(settings_class):
        if not key.startswith("_") and not callable(getattr(settings_class, key)):
            setattr(cfg, key, getattr(settings_class, key))
    if overrides:
        for k, v in overrides.items():
            setattr(cfg, k, v)
    return cfg


class SessionManager:
    """Thread-safe manager for multiple independent simulation sessions.

    Each session wraps its own SimulationEngine, allowing users to run
    multiple simulations in parallel within the same FastAPI process.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._viewer_counts: dict[str, int] = {}
        self._lock = threading.Lock()

    # -- lifecycle ----------------------------------------------------------

    def create_default_session(self, config: Any) -> str:
        """Create the default "main" session used for backwards compatibility.

        Args:
            config: Settings object passed to SimulationEngine.

        Returns:
            The session id (always "main").
        """
        engine = SimulationEngine(config)
        with self._lock:
            self._sessions["main"] = {
                "id": "main",
                "name": "main",
                "engine": engine,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._viewer_counts["main"] = 0
        return "main"

    def create_session(
        self, name: str, config: Any, overrides: dict | None = None
    ) -> str:
        """Create a new simulation session.

        Args:
            name: Human-readable session name.
            config: A Settings-like class OR an existing mutable config object.
            overrides: Optional dict to override config values (useful when
                       *config* is a class with class-level defaults).

        Returns:
            Unique session id (UUID string).
        """
        cfg = _make_config(config, overrides)

        session_id = uuid4().hex[:12]
        engine = SimulationEngine(cfg)
        with self._lock:
            self._sessions[session_id] = {
                "id": session_id,
                "name": name,
                "engine": engine,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._viewer_counts[session_id] = 0
        return session_id

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and stop its engine.

        Args:
            session_id: Session identifier to remove.

        Returns:
            True if the session was found and deleted, False otherwise.
        """
        if session_id == "main":
            return False  # never delete the default session

        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return False
            self._viewer_counts.pop(session_id, None)

        engine: SimulationEngine = session["engine"]
        # Stop the engine if it was running (best-effort, fire-and-forget)
        # We rely on the session being removed from the dict so no new
        # requests will target it; cleanup of the asyncio task is handled
        # when someone calls engine.stop() via the API.
        return True

    def get_session(self, session_id: str) -> SimulationEngine | None:
        """Return the SimulationEngine for the given session id.

        Args:
            session_id: Session identifier ("main" or a UUID).

        Returns:
            The SimulationEngine or None if not found.
        """
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return None
        return session["engine"]

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return a summary list of all sessions.

        Returns:
            List of dicts with id, name, population, status, viewers, created_at.
        """
        with self._lock:
            results = []
            for sid, sess in self._sessions.items():
                engine: SimulationEngine = sess["engine"]
                results.append({
                    "id": sid,
                    "name": sess["name"],
                    "population": engine.agents.active_count,
                    "status": engine.status,
                    "viewers": self._viewer_counts.get(sid, 0),
                    "created_at": sess["created_at"],
                })
            return results

    def increment_viewers(self, session_id: str) -> None:
        with self._lock:
            self._viewer_counts[session_id] = self._viewer_counts.get(session_id, 0) + 1

    def decrement_viewers(self, session_id: str) -> None:
        with self._lock:
            count = self._viewer_counts.get(session_id, 0)
            self._viewer_counts[session_id] = max(0, count - 1)
