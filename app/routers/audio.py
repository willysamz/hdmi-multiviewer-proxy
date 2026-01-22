"""Audio endpoints: source, volume, mute."""

from fastapi import APIRouter, HTTPException

from app.commands import Commands, ResponseParser
from app.dependencies import get_serial_handler
from app.models import (
    AUDIO_SOURCE_NAMES,
    AudioResponse,
    ErrorResponse,
    SetAudioSourceRequest,
    SetMuteRequest,
    SetVolumeRequest,
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


@router.get("/audio", response_model=AudioResponse)
async def get_audio() -> AudioResponse:
    """Get current audio settings (source, volume, mute)."""
    _check_device_available()
    handler = get_serial_handler()

    source = None
    volume = None
    muted = None

    # Get audio source
    success, response, _ = await handler.send_command(Commands.GET_AUDIO_SOURCE)
    if success and response:
        source = ResponseParser.parse_audio_source(response)

    # Get volume
    success, response, _ = await handler.send_command(Commands.GET_AUDIO_VOL)
    if success and response:
        volume = ResponseParser.parse_volume(response)

    # Get mute state
    success, response, _ = await handler.send_command(Commands.GET_AUDIO_MUTE)
    if success and response:
        muted = ResponseParser.parse_mute(response)

    return AudioResponse(
        source=source,
        source_name=AUDIO_SOURCE_NAMES.get(source) if source is not None else None,
        volume=volume,
        muted=muted,
    )


@router.post("/audio/source", response_model=AudioResponse)
async def set_audio_source(request: SetAudioSourceRequest) -> AudioResponse:
    """
    Set audio source.

    - 0: Follow window 1 selected source
    - 1: HDMI 1 input audio
    - 2: HDMI 2 input audio
    - 3: HDMI 3 input audio
    - 4: HDMI 4 input audio
    """
    _check_device_available()
    handler = get_serial_handler()

    command = Commands.SET_AUDIO_SOURCE.format(x=request.source)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set audio source",
                retry_after=5,
            ).model_dump(),
        )

    # Get full audio state
    return await get_audio()


@router.post("/audio/volume", response_model=AudioResponse)
async def set_audio_volume(request: SetVolumeRequest) -> AudioResponse:
    """Set audio volume (0-100)."""
    _check_device_available()
    handler = get_serial_handler()

    command = Commands.SET_AUDIO_VOL.format(x=request.volume)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set audio volume",
                retry_after=5,
            ).model_dump(),
        )

    # Get full audio state
    return await get_audio()


@router.post("/audio/volume/up", response_model=AudioResponse)
async def increase_volume() -> AudioResponse:
    """Increase audio volume by one step."""
    _check_device_available()
    handler = get_serial_handler()

    success, response, error = await handler.send_command(Commands.AUDIO_VOL_UP)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to increase volume",
                retry_after=5,
            ).model_dump(),
        )

    return await get_audio()


@router.post("/audio/volume/down", response_model=AudioResponse)
async def decrease_volume() -> AudioResponse:
    """Decrease audio volume by one step."""
    _check_device_available()
    handler = get_serial_handler()

    success, response, error = await handler.send_command(Commands.AUDIO_VOL_DOWN)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to decrease volume",
                retry_after=5,
            ).model_dump(),
        )

    return await get_audio()


@router.post("/audio/mute", response_model=AudioResponse)
async def set_audio_mute(request: SetMuteRequest) -> AudioResponse:
    """Set audio mute state."""
    _check_device_available()
    handler = get_serial_handler()

    mute_value = 1 if request.muted else 0
    command = Commands.SET_AUDIO_MUTE.format(x=mute_value)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set mute state",
                retry_after=5,
            ).model_dump(),
        )

    return await get_audio()


@router.post("/audio/mute/toggle", response_model=AudioResponse)
async def toggle_mute() -> AudioResponse:
    """Toggle audio mute state."""
    _check_device_available()
    handler = get_serial_handler()

    # Get current mute state
    success, response, _ = await handler.send_command(Commands.GET_AUDIO_MUTE)
    current_muted = False
    if success and response:
        current_muted = ResponseParser.parse_mute(response) or False

    # Toggle
    new_mute_value = 0 if current_muted else 1
    command = Commands.SET_AUDIO_MUTE.format(x=new_mute_value)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to toggle mute",
                retry_after=5,
            ).model_dump(),
        )

    return await get_audio()
