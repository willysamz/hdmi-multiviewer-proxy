"""System endpoints: status, power, reboot."""

from fastapi import APIRouter, HTTPException, Response

from app.commands import Commands, ResponseParser
from app.dependencies import get_serial_handler
from app.models import (
    ConnectionState,
    DeviceStatus,
    ErrorResponse,
    PowerRequest,
    PowerResponse,
)
from app.serial_handler import ConnectionState as HandlerConnectionState

router = APIRouter()


def _check_device_available() -> None:
    """Check if device is available, raise HTTPException if not."""
    handler = get_serial_handler()
    if handler.state == HandlerConnectionState.UNAVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="device_unavailable",
                message="Serial device not connected",
                retry_after=5,
            ).model_dump(),
        )


@router.get("/status", response_model=DeviceStatus)
async def get_status() -> DeviceStatus:
    """
    Get device status.

    Returns connection state, power state, device info, and firmware version.
    """
    handler = get_serial_handler()

    status = DeviceStatus(
        connection=ConnectionState(handler.state.value),
        port=handler.port,
        last_heartbeat=handler.last_heartbeat,
    )

    # If device is available, get additional info
    if handler.state != HandlerConnectionState.UNAVAILABLE:
        # Get power state
        success, response, _ = await handler.send_command(Commands.GET_POWER)
        if success and response:
            status.power = ResponseParser.parse_power(response)

        # Get device type
        success, response, _ = await handler.send_command(Commands.GET_TYPE)
        if success and response:
            status.device_type = response.strip()

        # Get firmware version
        success, response, _ = await handler.send_command(Commands.GET_FW_VERSION)
        if success and response:
            status.firmware = response.strip()

    return status


@router.post("/power", response_model=PowerResponse)
async def set_power(request: PowerRequest, response: Response) -> PowerResponse:
    """
    Set device power state.

    Power on or off the device.
    """
    _check_device_available()
    handler = get_serial_handler()

    command = Commands.POWER_ON if request.power else Commands.POWER_OFF
    success, resp, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set power state",
                retry_after=5,
            ).model_dump(),
        )

    # Verify the new state
    success, resp, _ = await handler.send_command(Commands.GET_POWER)
    power_state = ResponseParser.parse_power(resp) if success and resp else request.power

    return PowerResponse(power=power_state if power_state is not None else request.power)


@router.post("/reboot")
async def reboot_device() -> dict:
    """
    Reboot the device.

    The device will restart and take a few seconds to become available again.
    """
    _check_device_available()
    handler = get_serial_handler()

    success, response, error = await handler.send_command(Commands.REBOOT)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to reboot device",
                retry_after=5,
            ).model_dump(),
        )

    return {
        "message": "Device rebooting",
        "response": response,
    }


@router.post("/reset")
async def factory_reset() -> dict:
    """
    Reset device to factory defaults.

    WARNING: This will erase all settings and restore factory defaults.
    """
    _check_device_available()
    handler = get_serial_handler()

    success, response, error = await handler.send_command(Commands.RESET)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to reset device",
                retry_after=5,
            ).model_dump(),
        )

    return {
        "message": "Device reset to factory defaults",
        "response": response,
    }
