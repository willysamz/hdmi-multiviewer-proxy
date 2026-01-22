"""Health check endpoints for Kubernetes probes."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Response

from app.dependencies import get_serial_handler, get_startup_time
from app.models import ConnectionState, HealthResponse

HealthStatus = Literal["ok", "degraded", "error"]

router = APIRouter()


def _get_uptime_seconds() -> float:
    """Calculate uptime in seconds."""
    startup = get_startup_time()
    return (datetime.now(UTC) - startup).total_seconds()


@router.get("/healthz/live", response_model=HealthResponse)
async def liveness_probe(response: Response) -> HealthResponse:
    """
    Liveness probe for Kubernetes.

    Returns 200 if the FastAPI process is running.
    Used by Kubernetes to restart the pod if the process hangs.
    """
    try:
        handler = get_serial_handler()
        return HealthResponse(
            status="ok",
            serial_connected=handler.is_connected,
            device_state=ConnectionState(handler.state.value),
            last_heartbeat=handler.last_heartbeat,
            uptime_seconds=_get_uptime_seconds(),
        )
    except RuntimeError:
        # Handler not initialized yet
        return HealthResponse(
            status="ok",
            serial_connected=False,
            device_state=ConnectionState.UNAVAILABLE,
            last_heartbeat=None,
            uptime_seconds=_get_uptime_seconds(),
        )


@router.get("/healthz/ready", response_model=HealthResponse)
async def readiness_probe(response: Response) -> HealthResponse:
    """
    Readiness probe for Kubernetes.

    Returns 200 if the service can accept requests (serial handler initialized).
    Returns 503 if still initializing or in a bad state.
    Used by Kubernetes to remove pod from service endpoints during issues.
    """
    try:
        handler = get_serial_handler()

        if not handler.is_initialized:
            response.status_code = 503
            return HealthResponse(
                status="error",
                serial_connected=False,
                device_state=ConnectionState.UNAVAILABLE,
                last_heartbeat=None,
                uptime_seconds=_get_uptime_seconds(),
            )

        # Service is ready even if device is disconnected
        # (we gracefully handle disconnected state)
        status: HealthStatus = "ok" if handler.is_connected else "degraded"

        return HealthResponse(
            status=status,
            serial_connected=handler.is_connected,
            device_state=ConnectionState(handler.state.value),
            last_heartbeat=handler.last_heartbeat,
            uptime_seconds=_get_uptime_seconds(),
        )

    except RuntimeError:
        # Handler not initialized
        response.status_code = 503
        return HealthResponse(
            status="error",
            serial_connected=False,
            device_state=ConnectionState.UNAVAILABLE,
            last_heartbeat=None,
            uptime_seconds=_get_uptime_seconds(),
        )
