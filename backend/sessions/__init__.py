from backend.sessions.session_manager import SessionManager


def create_session_manager() -> SessionManager:
    """Factory helper for creating a SessionManager instance."""
    return SessionManager()


__all__ = ["SessionManager", "create_session_manager"]
