"""RS-232 command definitions and response parsers."""

import re
from enum import IntEnum


class MultiviewMode(IntEnum):
    """Multiview display modes."""

    SINGLE = 1
    PIP = 2
    PBP = 3
    TRIPLE = 4
    QUAD = 5


class AudioSource(IntEnum):
    """Audio source options."""

    FOLLOW_WINDOW_1 = 0
    HDMI_1 = 1
    HDMI_2 = 2
    HDMI_3 = 3
    HDMI_4 = 4


class HDMIInput(IntEnum):
    """HDMI input options."""

    HDMI_1 = 1
    HDMI_2 = 2
    HDMI_3 = 3
    HDMI_4 = 4


class PIPPosition(IntEnum):
    """PIP window positions."""

    LEFT_TOP = 1
    LEFT_BOTTOM = 2
    RIGHT_TOP = 3
    RIGHT_BOTTOM = 4


class PIPSize(IntEnum):
    """PIP window sizes."""

    SMALL = 1
    MIDDLE = 2
    LARGE = 3


class OutputResolution(IntEnum):
    """Output resolution options."""

    RES_4096x2160p60 = 1
    RES_4096x2160p50 = 2
    RES_3840x2160p60 = 3
    RES_3840x2160p50 = 4
    RES_3840x2160p30 = 5
    RES_3840x2160p25 = 6
    RES_1920x1200p60RB = 7
    RES_1920x1080p60 = 8
    RES_1920x1080p50 = 9
    RES_1360x768p60 = 10
    RES_1280x800p60 = 11
    RES_1280x720p60 = 12
    RES_1280x720p50 = 13
    RES_1024x768p60 = 14


RESOLUTION_NAMES = {
    OutputResolution.RES_4096x2160p60: "4096x2160p60",
    OutputResolution.RES_4096x2160p50: "4096x2160p50",
    OutputResolution.RES_3840x2160p60: "3840x2160p60",
    OutputResolution.RES_3840x2160p50: "3840x2160p50",
    OutputResolution.RES_3840x2160p30: "3840x2160p30",
    OutputResolution.RES_3840x2160p25: "3840x2160p25",
    OutputResolution.RES_1920x1200p60RB: "1920x1200p60RB",
    OutputResolution.RES_1920x1080p60: "1920x1080p60",
    OutputResolution.RES_1920x1080p50: "1920x1080p50",
    OutputResolution.RES_1360x768p60: "1360x768p60",
    OutputResolution.RES_1280x800p60: "1280x800p60",
    OutputResolution.RES_1280x720p60: "1280x720p60",
    OutputResolution.RES_1280x720p50: "1280x720p50",
    OutputResolution.RES_1024x768p60: "1024x768p60",
}


class HDCPMode(IntEnum):
    """HDCP mode options."""

    HDCP_1_4 = 1
    HDCP_2_2 = 2
    HDCP_OFF = 3


class VideoMode(IntEnum):
    """Video mode (ITC) options."""

    VIDEO_MODE = 1
    PC_MODE = 2


class VKAPattern(IntEnum):
    """Video keep active pattern options."""

    BLACK_SCREEN = 1
    BLUE_SCREEN = 2


class PBPMode(IntEnum):
    """PBP display modes."""

    MODE_1 = 1
    MODE_2 = 2


class AspectRatio(IntEnum):
    """Aspect ratio options."""

    FULL_SCREEN = 1
    RATIO_16_9 = 2


# Command templates
class Commands:
    """RS-232 command strings."""

    # System
    HELP = "help!"
    GET_TYPE = "r type!"
    GET_FW_VERSION = "r fw version!"
    POWER_ON = "power 1!"
    POWER_OFF = "power 0!"
    GET_POWER = "r power!"
    REBOOT = "reboot!"
    RESET = "reset!"

    # Output settings
    SET_OUTPUT_RES = "s output res {x}!"
    GET_OUTPUT_RES = "r output res!"
    SET_OUTPUT_HDCP = "s output hdcp {x}!"
    GET_OUTPUT_HDCP = "r output hdcp!"
    SET_OUTPUT_VKA = "s output vka {x}!"
    GET_OUTPUT_VKA = "r output vka!"
    SET_OUTPUT_ITC = "s output itc {x}!"
    GET_OUTPUT_ITC = "r output itc!"

    # EDID
    SET_INPUT_EDID = "s input EDID {x}!"
    GET_INPUT_EDID = "r input EDID!"

    # Audio
    SET_AUDIO_SOURCE = "s output audio {x}!"
    GET_AUDIO_SOURCE = "r output audio!"
    AUDIO_VOL_UP = "s output audio vol+!"
    AUDIO_VOL_DOWN = "s output audio vol-!"
    SET_AUDIO_VOL = "s output audio vol {x}!"
    GET_AUDIO_VOL = "r output audio vol!"
    SET_AUDIO_MUTE = "s output audio mute {x}!"
    GET_AUDIO_MUTE = "r output audio mute!"

    # Single screen mode
    SET_AUTO_SWITCH = "s auto switch {x}!"
    GET_AUTO_SWITCH = "r auto switch!"
    SET_INPUT_SOURCE = "s in source {x}!"
    GET_INPUT_SOURCE = "r in source!"

    # Multiview mode
    SET_MULTIVIEW = "s multiview {x}!"
    GET_MULTIVIEW = "r multiview!"
    SET_WINDOW_INPUT = "s window {x} in {y}!"
    GET_WINDOW_INPUT = "r window {x} in!"
    GET_ALL_WINDOWS_INPUT = "r window 0 in!"

    # PIP settings
    SET_PIP_POSITION = "s PIP position {x}!"
    GET_PIP_POSITION = "r PIP position!"
    SET_PIP_SIZE = "s PIP size {x}!"
    GET_PIP_SIZE = "r PIP size!"

    # PBP settings
    SET_PBP_MODE = "s PBP mode {x}!"
    GET_PBP_MODE = "r PBP mode!"
    SET_PBP_ASPECT = "s PBP aspect {x}!"
    GET_PBP_ASPECT = "r PBP aspect!"

    # Triple settings
    SET_TRIPLE_MODE = "s triple mode {x}!"
    GET_TRIPLE_MODE = "r triple mode!"
    SET_TRIPLE_ASPECT = "s triple aspect {x}!"
    GET_TRIPLE_ASPECT = "r triple aspect!"

    # Quad settings
    SET_QUAD_MODE = "s quad mode {x}!"
    GET_QUAD_MODE = "r quad mode!"
    SET_QUAD_ASPECT = "s quad aspect {x}!"
    GET_QUAD_ASPECT = "r quad aspect!"


# Response parsers
class ResponseParser:
    """Parse device responses into structured data."""

    @staticmethod
    def parse_power(response: str) -> bool | None:
        """Parse power state response."""
        if "power on" in response.lower():
            return True
        if "power off" in response.lower():
            return False
        return None

    @staticmethod
    def parse_multiview_mode(response: str) -> str | None:
        """Parse multiview mode response."""
        response_lower = response.lower()
        if "single" in response_lower:
            return "single"
        if "pip" in response_lower:
            return "pip"
        if "pbp" in response_lower:
            return "pbp"
        if "triple" in response_lower:
            return "triple"
        if "quad" in response_lower:
            return "quad"
        return None

    @staticmethod
    def parse_audio_source(response: str) -> int | None:
        """Parse audio source response."""
        response_lower = response.lower()
        if "follow" in response_lower:
            return 0
        if "hdmi 1" in response_lower:
            return 1
        if "hdmi 2" in response_lower:
            return 2
        if "hdmi 3" in response_lower:
            return 3
        if "hdmi 4" in response_lower:
            return 4
        return None

    @staticmethod
    def parse_volume(response: str) -> int | None:
        """Parse volume response."""
        match = re.search(r"volume:\s*(\d+)", response, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def parse_mute(response: str) -> bool | None:
        """Parse mute state response."""
        if "mute: on" in response.lower():
            return True
        if "mute: off" in response.lower():
            return False
        return None

    @staticmethod
    def parse_resolution(response: str) -> str | None:
        """Parse resolution response."""
        match = re.search(r"resolution:\s*(.+)", response, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def parse_hdcp(response: str) -> str | None:
        """Parse HDCP response."""
        response_lower = response.lower()
        if "hdcp 1.4" in response_lower:
            return "hdcp_1_4"
        if "hdcp 2.2" in response_lower:
            return "hdcp_2_2"
        if "hdcp off" in response_lower:
            return "off"
        return None

    @staticmethod
    def parse_video_mode(response: str) -> str | None:
        """Parse video mode (ITC) response."""
        response_lower = response.lower()
        if "video mode" in response_lower:
            return "video"
        if "pc mode" in response_lower:
            return "pc"
        return None

    @staticmethod
    def parse_window_input(response: str) -> int | None:
        """Parse window input selection response."""
        response_lower = response.lower()
        if "hdmi 1" in response_lower:
            return 1
        if "hdmi 2" in response_lower:
            return 2
        if "hdmi 3" in response_lower:
            return 3
        if "hdmi 4" in response_lower:
            return 4
        return None

    @staticmethod
    def parse_pip_position(response: str) -> str | None:
        """Parse PIP position response."""
        response_lower = response.lower()
        if "left top" in response_lower:
            return "left_top"
        if "left bottom" in response_lower:
            return "left_bottom"
        if "right top" in response_lower:
            return "right_top"
        if "right bottom" in response_lower:
            return "right_bottom"
        return None

    @staticmethod
    def parse_pip_size(response: str) -> str | None:
        """Parse PIP size response."""
        response_lower = response.lower()
        if "small" in response_lower:
            return "small"
        if "middle" in response_lower:
            return "middle"
        if "large" in response_lower:
            return "large"
        return None

    @staticmethod
    def parse_pbp_mode(response: str) -> int | None:
        """Parse PBP mode response."""
        if "mode 1" in response.lower():
            return 1
        if "mode 2" in response.lower():
            return 2
        return None

    @staticmethod
    def parse_aspect(response: str) -> str | None:
        """Parse aspect ratio response."""
        response_lower = response.lower()
        if "full" in response_lower:
            return "full_screen"
        if "16:9" in response_lower:
            return "16_9"
        return None

    @staticmethod
    def parse_input_source(response: str) -> int | None:
        """Parse single screen input source response."""
        response_lower = response.lower()
        if "hdmi 1" in response_lower:
            return 1
        if "hdmi 2" in response_lower:
            return 2
        if "hdmi 3" in response_lower:
            return 3
        if "hdmi 4" in response_lower:
            return 4
        return None

    @staticmethod
    def parse_auto_switch(response: str) -> bool | None:
        """Parse auto switch response."""
        if "auto switch on" in response.lower():
            return True
        if "auto switch off" in response.lower():
            return False
        return None
