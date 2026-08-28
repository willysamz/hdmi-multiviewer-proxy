"""Translates incoming MQTT commands into multiviewer serial commands.

Each HA entity's command topic maps to a template string on the active
DeviceProfile, formatted with the appropriate enum code and sent over the
existing serial handler. After every successful set, the poller is nudged for
an immediate state refresh so HA reflects the confirmed value quickly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.commands import (
    AudioSource,
    HDMIInput,
    MultiviewMode,
    PIPPosition,
    PIPSize,
)
from app.profiles import CAP_AUTO_SWITCH, CAP_EDID, CAP_VOLUME, get_profile

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
        self.profile = get_profile(settings.device_profile)

    # ---- High-level dispatchers (one per command topic) ----

    async def set_power(self, payload: str) -> None:
        if payload == "ON":
            await self._send(self.profile.POWER_ON, "power on")
        elif payload == "OFF":
            await self._send(self.profile.POWER_OFF, "power off")
        else:
            raise ControllerError(f"invalid power payload: {payload!r}")

    async def set_mode(self, payload: str) -> None:
        mode = _MODE_MAP.get(payload.strip().lower())
        if mode is None:
            raise ControllerError(
                f"invalid mode payload: {payload!r} (expected one of {sorted(_MODE_MAP)})"
            )
        await self._send(self.profile.SET_MULTIVIEW.format(x=int(mode)), f"set mode={payload}")

    async def set_window_input(self, window_n: int, payload: str) -> None:
        if not 1 <= window_n <= 4:
            raise ControllerError(f"invalid window number: {window_n}")
        hdmi = _WINDOW_INPUT_MAP.get(payload.strip().lower())
        if hdmi is None:
            raise ControllerError(f"invalid window input: {payload!r} (expected HDMI 1..4)")
        await self._send(
            self.profile.SET_WINDOW_INPUT.format(x=window_n, y=int(hdmi)),
            f"set window={window_n} input={payload}",
        )

    async def set_input_source(self, payload: str) -> None:
        hdmi = _WINDOW_INPUT_MAP.get(payload.strip().lower())
        if hdmi is None:
            raise ControllerError(f"invalid input source: {payload!r} (expected HDMI 1..4)")
        await self._send(
            self.profile.SET_INPUT_SOURCE.format(x=int(hdmi)),
            f"set input_source={payload}",
        )

    async def set_audio_source(self, payload: str) -> None:
        src = _AUDIO_SOURCE_MAP.get(payload.strip().lower())
        if src is None:
            raise ControllerError(
                f"invalid audio source: {payload!r} (expected Follow Window 1 or HDMI 1..4)"
            )
        await self._send(
            self.profile.SET_AUDIO_SOURCE.format(x=int(src)), f"set audio_source={payload}"
        )

    async def set_audio_volume(self, payload: str) -> None:
        if not self.profile.supports(CAP_VOLUME):
            raise ControllerError(f"{self.profile.key} has no volume command; refusing to send one")
        try:
            vol = int(float(payload.strip()))
        except ValueError as exc:
            raise ControllerError(f"invalid volume payload: {payload!r}") from exc
        if not 0 <= vol <= 100:
            raise ControllerError(f"volume out of range: {vol}")
        await self._send(self.profile.SET_AUDIO_VOL.format(x=vol), f"set audio_volume={vol}")

    async def set_audio_mute(self, payload: str) -> None:
        if payload == "ON":
            await self._send(self.profile.SET_AUDIO_MUTE.format(x=1), "set mute=on")
        elif payload == "OFF":
            await self._send(self.profile.SET_AUDIO_MUTE.format(x=0), "set mute=off")
        else:
            raise ControllerError(f"invalid mute payload: {payload!r}")

    async def set_pip_position(self, payload: str) -> None:
        pos = _PIP_POSITION_MAP.get(payload.strip().lower())
        if pos is None:
            raise ControllerError(
                f"invalid PIP position: {payload!r} (expected Top Left/Bottom Left/Top Right/Bottom Right)"
            )
        await self._send(
            self.profile.SET_PIP_POSITION.format(x=int(pos)), f"set pip_position={payload}"
        )

    async def set_pip_size(self, payload: str) -> None:
        sz = _PIP_SIZE_MAP.get(payload.strip().lower())
        if sz is None:
            raise ControllerError(f"invalid PIP size: {payload!r} (expected Small/Medium/Large)")
        await self._send(self.profile.SET_PIP_SIZE.format(x=int(sz)), f"set pip_size={payload}")

    async def set_auto_switch(self, payload: str) -> None:
        """Auto-switch: on signal loss the device jumps to the next live input.

        Worth being able to turn OFF -- it is a second actor changing inputs
        underneath scenes and scripts that set one explicitly.
        """
        if not self.profile.supports(CAP_AUTO_SWITCH):
            raise ControllerError(f"{self.profile.key} has no auto switch command")
        if payload == "ON":
            await self._send(self.profile.SET_AUTO_SWITCH.format(x=1), "set auto_switch=on")
        elif payload == "OFF":
            await self._send(self.profile.SET_AUTO_SWITCH.format(x=0), "set auto_switch=off")
        else:
            raise ControllerError(f"invalid auto switch payload: {payload!r}")

    async def set_edid(self, payload: str) -> None:
        """Set the EDID presented to all four inputs.

        Disruptive by nature: it renegotiates HDMI for every source, so a wrong
        value can black the display or drop audio. Validated strictly against
        the profile's option list -- an out-of-range index is refused rather
        than passed to the device.
        """
        if not self.profile.supports(CAP_EDID):
            raise ControllerError(f"{self.profile.key} has no EDID command")
        options = self.profile.edid_options
        want = payload.strip()
        try:
            index = next(i for i, opt in enumerate(options, start=1) if opt.lower() == want.lower())
        except StopIteration:
            raise ControllerError(
                f"invalid EDID mode: {payload!r} (expected one of {list(options)})"
            ) from None
        await self._send(self.profile.SET_INPUT_EDID.format(x=index), f"set edid={want}")

    # ---- low-level helpers ----

    async def _send(self, command: str, descr: str) -> None:
        log.info("mqtt_command_received", action=descr, command=command)
        success, response, error = await self.serial.send_command(command)
        if not success:
            log.warning("mqtt_command_failed", action=descr, error=error)
            raise ControllerError(f"serial command failed: {error}")
        # Nudge the poller so HA sees the confirmed state quickly.
        self.poller.trigger_immediate_poll()
