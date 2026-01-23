"""Pydantic models for API requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# Enums for API
class ConnectionState(str, Enum):
    """Device connection state."""

    UNAVAILABLE = "unavailable"
    OFF = "off"
    ON = "on"


class MultiviewModeEnum(str, Enum):
    """Multiview display modes."""

    SINGLE = "single"
    PIP = "pip"
    PBP = "pbp"
    TRIPLE = "triple"
    QUAD = "quad"


class AudioSourceEnum(str, Enum):
    """Audio source options."""

    FOLLOW_WINDOW_1 = "follow_window_1"
    HDMI_1 = "hdmi_1"
    HDMI_2 = "hdmi_2"
    HDMI_3 = "hdmi_3"
    HDMI_4 = "hdmi_4"


class HDMIInputEnum(str, Enum):
    """HDMI input options."""

    HDMI_1 = "hdmi_1"
    HDMI_2 = "hdmi_2"
    HDMI_3 = "hdmi_3"
    HDMI_4 = "hdmi_4"


class PIPPositionEnum(str, Enum):
    """PIP window positions."""

    LEFT_TOP = "left_top"
    LEFT_BOTTOM = "left_bottom"
    RIGHT_TOP = "right_top"
    RIGHT_BOTTOM = "right_bottom"


class PIPSizeEnum(str, Enum):
    """PIP window sizes."""

    SMALL = "small"
    MIDDLE = "middle"
    LARGE = "large"


class AspectRatioEnum(str, Enum):
    """Aspect ratio options."""

    FULL_SCREEN = "full_screen"
    RATIO_16_9 = "16_9"


class HDCPModeEnum(str, Enum):
    """HDCP mode options."""

    HDCP_1_4 = "hdcp_1_4"
    HDCP_2_2 = "hdcp_2_2"
    OFF = "off"


class VideoModeEnum(str, Enum):
    """Video mode options."""

    VIDEO = "video"
    PC = "pc"


# Health Models
class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["ok", "degraded", "error"]
    serial_connected: bool
    device_state: ConnectionState
    last_heartbeat: datetime | None
    uptime_seconds: float


# Error Models
class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    message: str
    retry_after: int | None = None


# System Models
class DeviceStatus(BaseModel):
    """Device status response."""

    connection: ConnectionState
    power: bool | None = None
    device_type: str | None = None
    firmware: str | None = None
    port: str
    last_heartbeat: datetime | None = None


class PowerRequest(BaseModel):
    """Power control request."""

    power: bool


class PowerResponse(BaseModel):
    """Power control response."""

    power: bool


# Display Models
class MultiviewResponse(BaseModel):
    """Multiview mode response."""

    mode: MultiviewModeEnum | None


class MultiviewRequest(BaseModel):
    """Multiview mode request."""

    mode: MultiviewModeEnum


class WindowInput(BaseModel):
    """Window input mapping."""

    window: int = Field(ge=1, le=4)
    input: int = Field(ge=0, le=4)  # 0 = unknown/unavailable
    input_name: str | None = None


class WindowsResponse(BaseModel):
    """All windows input mappings response."""

    windows: list[WindowInput]


class SetWindowInputRequest(BaseModel):
    """Set window input request."""

    input: int = Field(ge=1, le=4)


class InputSourceResponse(BaseModel):
    """Single screen input source response."""

    input: int | None
    input_name: str | None = None


class SetInputSourceRequest(BaseModel):
    """Set single screen input request."""

    input: int = Field(ge=1, le=4)


# Audio Models
class AudioResponse(BaseModel):
    """Audio state response."""

    source: int | None = None
    source_name: str | None = None
    volume: int | None = None
    muted: bool | None = None


class SetAudioSourceRequest(BaseModel):
    """Set audio source request."""

    source: int = Field(ge=0, le=4, description="0=follow window 1, 1-4=HDMI inputs")


class SetVolumeRequest(BaseModel):
    """Set volume request."""

    volume: int = Field(ge=0, le=100)


class SetMuteRequest(BaseModel):
    """Set mute request."""

    muted: bool


# Output Models
class OutputResponse(BaseModel):
    """Output settings response."""

    resolution: str | None = None
    hdcp: str | None = None
    video_mode: str | None = None
    vka_pattern: str | None = None


class SetResolutionRequest(BaseModel):
    """Set resolution request."""

    resolution: int = Field(ge=1, le=14)


class SetHDCPRequest(BaseModel):
    """Set HDCP request."""

    hdcp: int = Field(ge=1, le=3, description="1=HDCP 1.4, 2=HDCP 2.2, 3=OFF")


class SetVideoModeRequest(BaseModel):
    """Set video mode request."""

    mode: int = Field(ge=1, le=2, description="1=video, 2=pc")


# PIP Models
class PIPResponse(BaseModel):
    """PIP settings response."""

    position: str | None = None
    size: str | None = None


class SetPIPRequest(BaseModel):
    """Set PIP settings request."""

    position: int | None = Field(
        None, ge=1, le=4, description="1=left_top, 2=left_bottom, 3=right_top, 4=right_bottom"
    )
    size: int | None = Field(None, ge=1, le=3, description="1=small, 2=middle, 3=large")


# PBP Models
class PBPResponse(BaseModel):
    """PBP settings response."""

    mode: int | None = None
    aspect: str | None = None


class SetPBPRequest(BaseModel):
    """Set PBP settings request."""

    mode: int | None = Field(None, ge=1, le=2)
    aspect: int | None = Field(None, ge=1, le=2, description="1=full_screen, 2=16:9")


# Triple/Quad Models
class TripleQuadResponse(BaseModel):
    """Triple/Quad settings response."""

    mode: int | None = None
    aspect: str | None = None


class SetTripleQuadRequest(BaseModel):
    """Set Triple/Quad settings request."""

    mode: int | None = Field(None, ge=1, le=2)
    aspect: int | None = Field(None, ge=1, le=2, description="1=full_screen, 2=16:9")


# Mappings for friendly names
AUDIO_SOURCE_NAMES = {
    0: "follow_window_1",
    1: "hdmi_1",
    2: "hdmi_2",
    3: "hdmi_3",
    4: "hdmi_4",
}

INPUT_NAMES = {
    1: "hdmi_1",
    2: "hdmi_2",
    3: "hdmi_3",
    4: "hdmi_4",
}
