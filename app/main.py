"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI

from app import __version__
from app.config import settings
from app.dependencies import set_serial_handler, set_startup_time
from app.routers import audio, display, health, output, system
from app.serial_handler import SerialHandler

# Configure structured logging
LOG_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_renderer = (
    structlog.processors.JSONRenderer() if settings.log_json else structlog.dev.ConsoleRenderer()
)
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _renderer,  # type: ignore[list-item]
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        LOG_LEVELS.get(settings.log_level.upper(), 20)
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    set_startup_time(datetime.now(UTC))
    log.info("starting_application", version=__version__, port=settings.server_port)

    # Initialize serial handler
    serial_handler = SerialHandler(
        port=settings.serial_port,
        baud_rate=settings.serial_baud_rate,
        timeout=settings.serial_timeout,
        heartbeat_interval=settings.serial_heartbeat_interval,
        reconnect_backoff_max=settings.serial_reconnect_backoff_max,
    )
    set_serial_handler(serial_handler)

    # Start the serial handler
    await serial_handler.start()

    yield

    # Cleanup
    log.info("shutting_down_application")
    await serial_handler.stop()


app = FastAPI(
    title="HDMI Multiviewer Proxy",
    description="REST API for controlling UHD-401MV multiviewer via RS-232",
    version=__version__,
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(system.router, prefix="/api", tags=["System"])
app.include_router(display.router, prefix="/api", tags=["Display"])
app.include_router(audio.router, prefix="/api", tags=["Audio"])
app.include_router(output.router, prefix="/api", tags=["Output"])


@app.get("/")
async def root() -> dict:
    """Root endpoint with API info."""
    return {
        "name": "HDMI Multiviewer Proxy",
        "version": __version__,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
    )
