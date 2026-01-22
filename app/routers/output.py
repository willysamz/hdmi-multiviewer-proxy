"""Output endpoints: resolution, HDCP, video mode."""

from fastapi import APIRouter, HTTPException

from app.commands import RESOLUTION_NAMES, Commands, OutputResolution, ResponseParser
from app.dependencies import get_serial_handler
from app.models import (
    ErrorResponse,
    OutputResponse,
    SetHDCPRequest,
    SetResolutionRequest,
    SetVideoModeRequest,
)
from app.serial_handler import ConnectionState

router = APIRouter()


def _check_device_available() -> None:
    """Check if device is available, raise HTTPException if not."""
    handler = get_serial_handler()
    if handler.state == ConnectionState.UNAVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="device_unavailable",
                message="Serial device not connected",
                retry_after=5,
            ).model_dump(),
        )


@router.get("/output", response_model=OutputResponse)
async def get_output() -> OutputResponse:
    """Get current output settings (resolution, HDCP, video mode)."""
    _check_device_available()
    handler = get_serial_handler()

    resolution = None
    hdcp = None
    video_mode = None
    vka_pattern = None

    # Get resolution
    success, response, _ = await handler.send_command(Commands.GET_OUTPUT_RES)
    if success and response:
        resolution = ResponseParser.parse_resolution(response)

    # Get HDCP
    success, response, _ = await handler.send_command(Commands.GET_OUTPUT_HDCP)
    if success and response:
        hdcp = ResponseParser.parse_hdcp(response)

    # Get video mode (ITC)
    success, response, _ = await handler.send_command(Commands.GET_OUTPUT_ITC)
    if success and response:
        video_mode = ResponseParser.parse_video_mode(response)

    # Get VKA pattern
    success, response, _ = await handler.send_command(Commands.GET_OUTPUT_VKA)
    if success and response:
        if "black" in response.lower():
            vka_pattern = "black_screen"
        elif "blue" in response.lower():
            vka_pattern = "blue_screen"

    return OutputResponse(
        resolution=resolution,
        hdcp=hdcp,
        video_mode=video_mode,
        vka_pattern=vka_pattern,
    )


@router.post("/output/resolution", response_model=OutputResponse)
async def set_resolution(request: SetResolutionRequest) -> OutputResponse:
    """
    Set output resolution.

    Resolution values:
    - 1: 4096x2160p60
    - 2: 4096x2160p50
    - 3: 3840x2160p60
    - 4: 3840x2160p50
    - 5: 3840x2160p30
    - 6: 3840x2160p25
    - 7: 1920x1200p60RB
    - 8: 1920x1080p60
    - 9: 1920x1080p50
    - 10: 1360x768p60
    - 11: 1280x800p60
    - 12: 1280x720p60
    - 13: 1280x720p50
    - 14: 1024x768p60
    """
    _check_device_available()
    handler = get_serial_handler()

    command = Commands.SET_OUTPUT_RES.format(x=request.resolution)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set resolution",
                retry_after=5,
            ).model_dump(),
        )

    return await get_output()


@router.get("/output/resolutions")
async def get_available_resolutions() -> dict:
    """Get list of available output resolutions."""
    return {
        "resolutions": [
            {"value": res.value, "name": RESOLUTION_NAMES[res]} for res in OutputResolution
        ]
    }


@router.post("/output/hdcp", response_model=OutputResponse)
async def set_hdcp(request: SetHDCPRequest) -> OutputResponse:
    """
    Set HDCP mode.

    - 1: HDCP 1.4
    - 2: HDCP 2.2
    - 3: OFF
    """
    _check_device_available()
    handler = get_serial_handler()

    command = Commands.SET_OUTPUT_HDCP.format(x=request.hdcp)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set HDCP mode",
                retry_after=5,
            ).model_dump(),
        )

    return await get_output()


@router.post("/output/video-mode", response_model=OutputResponse)
async def set_video_mode(request: SetVideoModeRequest) -> OutputResponse:
    """
    Set video mode (ITC).

    - 1: Video mode
    - 2: PC mode
    """
    _check_device_available()
    handler = get_serial_handler()

    command = Commands.SET_OUTPUT_ITC.format(x=request.mode)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set video mode",
                retry_after=5,
            ).model_dump(),
        )

    return await get_output()


@router.post("/output/vka")
async def set_vka_pattern(pattern: int) -> OutputResponse:
    """
    Set video keep active pattern.

    - 1: Black screen
    - 2: Blue screen
    """
    if pattern not in (1, 2):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="invalid_parameter",
                message="Pattern must be 1 (black) or 2 (blue)",
            ).model_dump(),
        )

    _check_device_available()
    handler = get_serial_handler()

    command = Commands.SET_OUTPUT_VKA.format(x=pattern)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set VKA pattern",
                retry_after=5,
            ).model_dump(),
        )

    return await get_output()
