"""Application dependencies and shared state."""

from datetime import UTC, datetime

from app.serial_handler import SerialHandler

# Global state
_serial_handler: SerialHandler | None = None
_startup_time: datetime | None = None


def set_serial_handler(handler: SerialHandler) -> None:
    """Set the global serial handler instance."""
    global _serial_handler
    _serial_handler = handler


def get_serial_handler() -> SerialHandler:
    """Get the serial handler instance."""
    if _serial_handler is None:
        raise RuntimeError("Serial handler not initialized")
    return _serial_handler


def set_startup_time(time: datetime) -> None:
    """Set the application startup time."""
    global _startup_time
    _startup_time = time


def get_startup_time() -> datetime:
    """Get the application startup time."""
    if _startup_time is None:
        return datetime.now(UTC)
    return _startup_time
