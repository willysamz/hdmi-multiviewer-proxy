"""Translates incoming MQTT commands into multiviewer serial commands.

Each HA entity's command topic maps to a `Commands.*` template string,
formatted with the appropriate enum code and sent over the existing
serial handler. After every successful set, the poller is nudged for
an immediate state refresh so HA reflects the confirmed value quickly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.commands import (
    AudioSource,
    Commands,
    HDMIInput,
    MultiviewMode,
    PIPPosition,
    PIPSize,
)

if TYPE_CHECKING:
    from app.config import Settings
    from app.mqtt_client import MqttClient
    from app.poller import Poller
    from app.serial_handler import SerialHandler

log = structlog.get_logger()


class ControllerError(Exception):
    """Raised on a command-processing failure (invalid payload, bad mapping)."""


# String → enum maps. The strings here MUST match the discovery
# `options[]` lists in app/discovery.py.
_MODE_MAP = {
    "single": MultiviewMode.SINGLE,
    "pip": MultiviewMode.PIP,
    "pbp": MultiviewMode.PBP,
    "triple": MultiviewMode.TRIPLE,
    "quad": MultiviewMode.QUAD,
}
_WINDOW_INPUT_MAP = {
    "hdmi 1": HDMIInput.HDMI_1,
    "hdmi 2": HDMIInput.HDMI_2,
    "hdmi 3": HDMIInput.HDMI_3,
    "hdmi 4": HDMIInput.HDMI_4,
}
_AUDIO_SOURCE_MAP = {
    "follow window 1": AudioSource.FOLLOW_WINDOW_1,
    "hdmi 1": AudioSource.HDMI_1,
    "hdmi 2": AudioSource.HDMI_2,
    "hdmi 3": AudioSource.HDMI_3,
    "hdmi 4": AudioSource.HDMI_4,
}
_PIP_POSITION_MAP = {
    "top left": PIPPosition.LEFT_TOP,
    "bottom left": PIPPosition.LEFT_BOTTOM,
    "top right": PIPPosition.RIGHT_TOP,
    "bottom right": PIPPosition.RIGHT_BOTTOM,
}
_PIP_SIZE_MAP = {
    "small": PIPSize.SMALL,
    "medium": PIPSize.MIDDLE,
    "large": PIPSize.LARGE,
}


class Controller:
    """Routes MQTT-received commands to the multiviewer over serial."""

    def __init__(
        self,
        serial: SerialHandler,
        mqtt: MqttClient,
        poller: Poller,
        settings: Settings,
    ) -> None:
        self.serial = serial
        self.mqtt = mqtt
        self.poller = poller
        self.settings = settings

    # ---- High-level dispatchers (one per command topic) ----

    async def set_power(self, payload: str) -> None:
        if payload == "ON":
            await self._send(Commands.POWER_ON, "power on")
        elif payload == "OFF":
            await self._send(Commands.POWER_OFF, "power off")
        else:
            raise ControllerError(f"invalid power payload: {payload!r}")

    async def set_mode(self, payload: str) -> None:
        mode = _MODE_MAP.get(payload.strip().lower())
        if mode is None:
            raise ControllerError(
                f"invalid mode payload: {payload!r} (expected one of {sorted(_MODE_MAP)})"
            )
        await self._send(Commands.SET_MULTIVIEW.format(x=int(mode)), f"set mode={payload}")

    async def set_window_input(self, window_n: int, payload: str) -> None:
        if not 1 <= window_n <= 4:
            raise ControllerError(f"invalid window number: {window_n}")
        hdmi = _WINDOW_INPUT_MAP.get(payload.strip().lower())
        if hdmi is None:
            raise ControllerError(
                f"invalid window input: {payload!r} (expected HDMI 1..4)"
            )
        await self._send(
            Commands.SET_WINDOW_INPUT.format(x=window_n, y=int(hdmi)),
            f"set window={window_n} input={payload}",
        )

    async def set_audio_source(self, payload: str) -> None:
        src = _AUDIO_SOURCE_MAP.get(payload.strip().lower())
        if src is None:
            raise ControllerError(
                f"invalid audio source: {payload!r} (expected Follow Window 1 or HDMI 1..4)"
            )
        await self._send(
            Commands.SET_AUDIO_SOURCE.format(x=int(src)), f"set audio_source={payload}"
        )

    async def set_audio_volume(self, payload: str) -> None:
        try:
            vol = int(float(payload.strip()))
        except ValueError as exc:
            raise ControllerError(f"invalid volume payload: {payload!r}") from exc
        if not 0 <= vol <= 100:
            raise ControllerError(f"volume out of range: {vol}")
        await self._send(Commands.SET_AUDIO_VOL.format(x=vol), f"set audio_volume={vol}")

    async def set_audio_mute(self, payload: str) -> None:
        if payload == "ON":
            await self._send(Commands.SET_AUDIO_MUTE.format(x=1), "set mute=on")
        elif payload == "OFF":
            await self._send(Commands.SET_AUDIO_MUTE.format(x=0), "set mute=off")
        else:
            raise ControllerError(f"invalid mute payload: {payload!r}")

    async def set_pip_position(self, payload: str) -> None:
        pos = _PIP_POSITION_MAP.get(payload.strip().lower())
        if pos is None:
            raise ControllerError(
                f"invalid PIP position: {payload!r} (expected Top Left/Bottom Left/Top Right/Bottom Right)"
            )
        await self._send(
            Commands.SET_PIP_POSITION.format(x=int(pos)), f"set pip_position={payload}"
        )

    async def set_pip_size(self, payload: str) -> None:
        sz = _PIP_SIZE_MAP.get(payload.strip().lower())
        if sz is None:
            raise ControllerError(
                f"invalid PIP size: {payload!r} (expected Small/Medium/Large)"
            )
        await self._send(Commands.SET_PIP_SIZE.format(x=int(sz)), f"set pip_size={payload}")

    # ---- low-level helpers ----

    async def _send(self, command: str, descr: str) -> None:
        log.info("mqtt_command_received", action=descr, command=command)
        success, response, error = await self.serial.send_command(command)
        if not success:
            log.warning("mqtt_command_failed", action=descr, error=error)
            raise ControllerError(f"serial command failed: {error}")
        # Nudge the poller so HA sees the confirmed state quickly.
        self.poller.trigger_immediate_poll()
