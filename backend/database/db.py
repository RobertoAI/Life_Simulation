"""Database initialization and connection utilities."""

import os
import sqlite3

from backend.database.models import CREATE_TABLES_SQL


def init_db(db_path: str) -> str:
    """Initialize the database: create data directory and all tables.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The absolute path to the created database.
    """
    # Ensure the parent directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.executescript(CREATE_TABLES_SQL)
    conn.close()
    return db_path


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get a database connection with WAL mode enabled.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A sqlite3.Connection object.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn
