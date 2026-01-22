"""Display endpoints: multiview mode, window routing, PIP/PBP settings."""

from fastapi import APIRouter, HTTPException, Path

from app.commands import Commands, ResponseParser
from app.dependencies import get_serial_handler
from app.models import (
    INPUT_NAMES,
    ErrorResponse,
    InputSourceResponse,
    MultiviewModeEnum,
    MultiviewRequest,
    MultiviewResponse,
    PBPResponse,
    PIPResponse,
    SetInputSourceRequest,
    SetPBPRequest,
    SetPIPRequest,
    SetTripleQuadRequest,
    SetWindowInputRequest,
    TripleQuadResponse,
    WindowInput,
    WindowsResponse,
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


# Multiview mode endpoints
@router.get("/multiview", response_model=MultiviewResponse)
async def get_multiview() -> MultiviewResponse:
    """Get current multiview display mode."""
    _check_device_available()
    handler = get_serial_handler()

    success, response, _ = await handler.send_command(Commands.GET_MULTIVIEW)
    mode = None
    if success and response:
        mode_str = ResponseParser.parse_multiview_mode(response)
        if mode_str:
            mode = MultiviewModeEnum(mode_str)

    return MultiviewResponse(mode=mode)


@router.post("/multiview", response_model=MultiviewResponse)
async def set_multiview(request: MultiviewRequest) -> MultiviewResponse:
    """Set multiview display mode."""
    _check_device_available()
    handler = get_serial_handler()

    # Map mode to command value
    mode_map = {
        MultiviewModeEnum.SINGLE: 1,
        MultiviewModeEnum.PIP: 2,
        MultiviewModeEnum.PBP: 3,
        MultiviewModeEnum.TRIPLE: 4,
        MultiviewModeEnum.QUAD: 5,
    }

    command = Commands.SET_MULTIVIEW.format(x=mode_map[request.mode])
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set multiview mode",
                retry_after=5,
            ).model_dump(),
        )

    return MultiviewResponse(mode=request.mode)


# Window input routing endpoints
@router.get("/windows", response_model=WindowsResponse)
async def get_windows() -> WindowsResponse:
    """Get all window-to-input mappings."""
    _check_device_available()
    handler = get_serial_handler()

    windows = []
    for window_id in range(1, 5):
        command = Commands.GET_WINDOW_INPUT.format(x=window_id)
        success, response, _ = await handler.send_command(command)
        input_num = None
        if success and response:
            input_num = ResponseParser.parse_window_input(response)

        windows.append(
            WindowInput(
                window=window_id,
                input=input_num or 0,
                input_name=INPUT_NAMES.get(input_num) if input_num else None,
            )
        )

    return WindowsResponse(windows=windows)


@router.get("/windows/{window_id}", response_model=WindowInput)
async def get_window_input(
    window_id: int = Path(ge=1, le=4, description="Window ID (1-4)"),
) -> WindowInput:
    """Get input source for a specific window."""
    _check_device_available()
    handler = get_serial_handler()

    command = Commands.GET_WINDOW_INPUT.format(x=window_id)
    success, response, _ = await handler.send_command(command)

    input_num = None
    if success and response:
        input_num = ResponseParser.parse_window_input(response)

    return WindowInput(
        window=window_id,
        input=input_num or 0,
        input_name=INPUT_NAMES.get(input_num) if input_num else None,
    )


@router.post("/windows/{window_id}/input", response_model=WindowInput)
async def set_window_input(
    request: SetWindowInputRequest,
    window_id: int = Path(ge=1, le=4, description="Window ID (1-4)"),
) -> WindowInput:
    """Set input source for a specific window."""
    _check_device_available()
    handler = get_serial_handler()

    command = Commands.SET_WINDOW_INPUT.format(x=window_id, y=request.input)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set window input",
                retry_after=5,
            ).model_dump(),
        )

    return WindowInput(
        window=window_id,
        input=request.input,
        input_name=INPUT_NAMES.get(request.input),
    )


# Single screen mode endpoints
@router.get("/input", response_model=InputSourceResponse)
async def get_input_source() -> InputSourceResponse:
    """Get current input source (single screen mode)."""
    _check_device_available()
    handler = get_serial_handler()

    success, response, _ = await handler.send_command(Commands.GET_INPUT_SOURCE)
    input_num = None
    if success and response:
        input_num = ResponseParser.parse_input_source(response)

    return InputSourceResponse(
        input=input_num,
        input_name=INPUT_NAMES.get(input_num) if input_num else None,
    )


@router.post("/input", response_model=InputSourceResponse)
async def set_input_source(request: SetInputSourceRequest) -> InputSourceResponse:
    """Set input source (single screen mode)."""
    _check_device_available()
    handler = get_serial_handler()

    command = Commands.SET_INPUT_SOURCE.format(x=request.input)
    success, response, error = await handler.send_command(command)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error="command_failed",
                message=error or "Failed to set input source",
                retry_after=5,
            ).model_dump(),
        )

    return InputSourceResponse(
        input=request.input,
        input_name=INPUT_NAMES.get(request.input),
    )


# PIP settings endpoints
@router.get("/pip", response_model=PIPResponse)
async def get_pip_settings() -> PIPResponse:
    """Get PIP window settings."""
    _check_device_available()
    handler = get_serial_handler()

    position = None
    size = None

    success, response, _ = await handler.send_command(Commands.GET_PIP_POSITION)
    if success and response:
        position = ResponseParser.parse_pip_position(response)

    success, response, _ = await handler.send_command(Commands.GET_PIP_SIZE)
    if success and response:
        size = ResponseParser.parse_pip_size(response)

    return PIPResponse(position=position, size=size)


@router.post("/pip", response_model=PIPResponse)
async def set_pip_settings(request: SetPIPRequest) -> PIPResponse:
    """Set PIP window settings."""
    _check_device_available()
    handler = get_serial_handler()

    position = None
    size = None

    if request.position is not None:
        command = Commands.SET_PIP_POSITION.format(x=request.position)
        success, response, error = await handler.send_command(command)
        if not success:
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error="command_failed",
                    message=error or "Failed to set PIP position",
                    retry_after=5,
                ).model_dump(),
            )
        position = ResponseParser.parse_pip_position(response) if response else None

    if request.size is not None:
        command = Commands.SET_PIP_SIZE.format(x=request.size)
        success, response, error = await handler.send_command(command)
        if not success:
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error="command_failed",
                    message=error or "Failed to set PIP size",
                    retry_after=5,
                ).model_dump(),
            )
        size = ResponseParser.parse_pip_size(response) if response else None

    # Get current settings if not set
    if position is None:
        success, response, _ = await handler.send_command(Commands.GET_PIP_POSITION)
        if success and response:
            position = ResponseParser.parse_pip_position(response)

    if size is None:
        success, response, _ = await handler.send_command(Commands.GET_PIP_SIZE)
        if success and response:
            size = ResponseParser.parse_pip_size(response)

    return PIPResponse(position=position, size=size)


# PBP settings endpoints
@router.get("/pbp", response_model=PBPResponse)
async def get_pbp_settings() -> PBPResponse:
    """Get PBP window settings."""
    _check_device_available()
    handler = get_serial_handler()

    mode = None
    aspect = None

    success, response, _ = await handler.send_command(Commands.GET_PBP_MODE)
    if success and response:
        mode = ResponseParser.parse_pbp_mode(response)

    success, response, _ = await handler.send_command(Commands.GET_PBP_ASPECT)
    if success and response:
        aspect = ResponseParser.parse_aspect(response)

    return PBPResponse(mode=mode, aspect=aspect)


@router.post("/pbp", response_model=PBPResponse)
async def set_pbp_settings(request: SetPBPRequest) -> PBPResponse:
    """Set PBP window settings."""
    _check_device_available()
    handler = get_serial_handler()

    if request.mode is not None:
        command = Commands.SET_PBP_MODE.format(x=request.mode)
        success, _, error = await handler.send_command(command)
        if not success:
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error="command_failed",
                    message=error or "Failed to set PBP mode",
                    retry_after=5,
                ).model_dump(),
            )

    if request.aspect is not None:
        command = Commands.SET_PBP_ASPECT.format(x=request.aspect)
        success, _, error = await handler.send_command(command)
        if not success:
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error="command_failed",
                    message=error or "Failed to set PBP aspect",
                    retry_after=5,
                ).model_dump(),
            )

    # Get current settings
    return await get_pbp_settings()


# Triple screen settings endpoints
@router.get("/triple", response_model=TripleQuadResponse)
async def get_triple_settings() -> TripleQuadResponse:
    """Get triple screen settings."""
    _check_device_available()
    handler = get_serial_handler()

    mode = None
    aspect = None

    success, response, _ = await handler.send_command(Commands.GET_TRIPLE_MODE)
    if success and response:
        mode = ResponseParser.parse_pbp_mode(response)  # Same format as PBP

    success, response, _ = await handler.send_command(Commands.GET_TRIPLE_ASPECT)
    if success and response:
        aspect = ResponseParser.parse_aspect(response)

    return TripleQuadResponse(mode=mode, aspect=aspect)


@router.post("/triple", response_model=TripleQuadResponse)
async def set_triple_settings(request: SetTripleQuadRequest) -> TripleQuadResponse:
    """Set triple screen settings."""
    _check_device_available()
    handler = get_serial_handler()

    if request.mode is not None:
        command = Commands.SET_TRIPLE_MODE.format(x=request.mode)
        success, _, error = await handler.send_command(command)
        if not success:
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error="command_failed",
                    message=error or "Failed to set triple mode",
                    retry_after=5,
                ).model_dump(),
            )

    if request.aspect is not None:
        command = Commands.SET_TRIPLE_ASPECT.format(x=request.aspect)
        success, _, error = await handler.send_command(command)
        if not success:
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error="command_failed",
                    message=error or "Failed to set triple aspect",
                    retry_after=5,
                ).model_dump(),
            )

    return await get_triple_settings()


# Quad screen settings endpoints
@router.get("/quad", response_model=TripleQuadResponse)
async def get_quad_settings() -> TripleQuadResponse:
    """Get quad screen settings."""
    _check_device_available()
    handler = get_serial_handler()

    mode = None
    aspect = None

    success, response, _ = await handler.send_command(Commands.GET_QUAD_MODE)
    if success and response:
        mode = ResponseParser.parse_pbp_mode(response)

    success, response, _ = await handler.send_command(Commands.GET_QUAD_ASPECT)
    if success and response:
        aspect = ResponseParser.parse_aspect(response)

    return TripleQuadResponse(mode=mode, aspect=aspect)


@router.post("/quad", response_model=TripleQuadResponse)
async def set_quad_settings(request: SetTripleQuadRequest) -> TripleQuadResponse:
    """Set quad screen settings."""
    _check_device_available()
    handler = get_serial_handler()

    if request.mode is not None:
        command = Commands.SET_QUAD_MODE.format(x=request.mode)
        success, _, error = await handler.send_command(command)
        if not success:
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error="command_failed",
                    message=error or "Failed to set quad mode",
                    retry_after=5,
                ).model_dump(),
            )

    if request.aspect is not None:
        command = Commands.SET_QUAD_ASPECT.format(x=request.aspect)
        success, _, error = await handler.send_command(command)
        if not success:
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error="command_failed",
                    message=error or "Failed to set quad aspect",
                    retry_after=5,
                ).model_dump(),
            )

    return await get_quad_settings()
