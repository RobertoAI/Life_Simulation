"""structlog configuration for the simulation backend."""

import structlog


def get_logger(name: str = "simulator"):
    """Create a structured logger with JSON output to stdout.

    Args:
        name: Logger name prefix.

    Returns:
        A structlog BoundLogger instance.
    """
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger(name)
