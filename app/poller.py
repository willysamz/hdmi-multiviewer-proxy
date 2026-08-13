"""Background poll loop: serial → publish state + discovery to MQTT.

The multiviewer doesn't have a unified state-read endpoint, so each
poll cycle issues a handful of serial commands (one per entity group)
and parses each response. Deltas are published to retained MQTT
topics; the full discovery payload is emitted once on the first
successful cycle.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from app.commands import (
    Commands,
    ResponseParser,
)
from app.discovery import (
    audio_source_select_payload,
    connected_binary_sensor_payload,
    input_source_select_payload,
    mode_select_payload,
    mute_switch_payload,
    pip_position_select_payload,
    pip_size_select_payload,
    power_switch_payload,
    resolution_sensor_payload,
    volume_number_payload,
    window_select_payload,
)
from app.serial_handler import ConnectionState

if TYPE_CHECKING:
    from app.config import Settings
    from app.mqtt_client import MqttClient
    from app.serial_handler import SerialHandler

log = structlog.get_logger()

# Mapping from the parsed audio-source code (0=Follow Window 1, 1..4=HDMI N)
# back to the human-readable label used as the `select` entity's state.
_AUDIO_SOURCE_CODE_TO_NAME = {
    0: "Follow Window 1",
    1: "HDMI 1",
    2: "HDMI 2",
    3: "HDMI 3",
    4: "HDMI 4",
}

# Parser returns lower-cased keys; map to the dashboard-friendly labels
# used in discovery `options[]`.
_PIP_POSITION_TO_NAME = {
    "left_top": "Top Left",
    "left_bottom": "Bottom Left",
    "right_top": "Top Right",
    "right_bottom": "Bottom Right",
}
_PIP_SIZE_TO_NAME = {
    "small": "Small",
    "middle": "Medium",
    "large": "Large",
}


class Poller:
    """Polls the multiviewer on a fixed cadence and publishes to MQTT."""

    def __init__(
        self,
        serial: SerialHandler,
        mqtt: MqttClient,
        settings: Settings,
    ) -> None:
        self.serial = serial
        self.mqtt = mqtt
        self.settings = settings

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._immediate_event = asyncio.Event()

        self._discovery_published = False
        # Per-topic last-published cache so we publish deltas only.
        self._last: dict[str, str] = {}

    def trigger_immediate_poll(self) -> None:
        """Skip the sleep on the next iteration and poll right now."""
        self._immediate_event.set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except TimeoutError:
                self._task.cancel()

    async def _run(self) -> None:
        await asyncio.sleep(2)
        while not self._stop_event.is_set():
            try:
                await self.poll_once()
            except Exception as exc:
                log.warning("poll_cycle_failed", error=str(exc))

            self._immediate_event.clear()
            stop_task = asyncio.create_task(self._stop_event.wait())
            immediate_task = asyncio.create_task(self._immediate_event.wait())
            done, pending = await asyncio.wait(
                {stop_task, immediate_task},
                timeout=self.settings.poll_interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            if not done:  # pragma: no cover
                continue

    async def poll_once(self) -> None:
        """One cycle: query each entity group + publish deltas."""
        # Always publish discovery on first cycle (even if some queries fail).
        if not self._discovery_published:
            await self._publish_discovery()
            self._discovery_published = True

        prefix = self.settings.mqtt_topic_prefix.strip("/")

        # Connectivity: derived from the serial handler's state property.
        connected = self.serial.state == ConnectionState.ON
        await self._publish_delta(f"{prefix}/connected/state", "ON" if connected else "OFF")

        # Power: prefer the device's own r power! answer whenever the transport
        # is open; fall back to OFF only when the read fails / port is down.
        # Gated on the LIVE transport status (is_connected), not the cached
        # `state` (which only updates at connect + the 30s heartbeat and would
        # otherwise republish a stale value for up to 30s).
        power = None
        if self.serial.is_connected:
            power = await self._read(Commands.GET_POWER, ResponseParser.parse_power)
        if power is None:
            await self._publish_delta(
                f"{prefix}/power/state", "ON" if self.serial.is_connected else "OFF"
            )
        else:
            await self._publish_delta(f"{prefix}/power/state", "ON" if power else "OFF")

        # The remaining queries only work when the device is powered ON.
        if not connected:
            return

        # Mode
        mode = await self._read(Commands.GET_MULTIVIEW, ResponseParser.parse_multiview_mode)
        if mode is not None:
            await self._publish_delta(f"{prefix}/mode/state", mode)

        # Windows 1..4
        for n in range(1, 5):
            cmd = Commands.GET_WINDOW_INPUT.format(x=n)
            window_in = await self._read(cmd, ResponseParser.parse_window_input)
            if window_in is not None:
                await self._publish_delta(f"{prefix}/windows/{n}/state", f"HDMI {window_in}")

        # Single-screen input source (drives single mode; s in source)
        in_src = await self._read(Commands.GET_INPUT_SOURCE, ResponseParser.parse_input_source)
        if in_src is not None:
            await self._publish_delta(f"{prefix}/input/source/state", f"HDMI {in_src}")

        # Audio source / volume / mute
        audio_src = await self._read(Commands.GET_AUDIO_SOURCE, ResponseParser.parse_audio_source)
        if audio_src is not None:
            name = _AUDIO_SOURCE_CODE_TO_NAME.get(audio_src, f"HDMI {audio_src}")
            await self._publish_delta(f"{prefix}/audio/source/state", name)

        vol = await self._read(Commands.GET_AUDIO_VOL, ResponseParser.parse_volume)
        if vol is not None:
            await self._publish_delta(f"{prefix}/audio/volume/state", str(vol))

        muted = await self._read(Commands.GET_AUDIO_MUTE, ResponseParser.parse_mute)
        if muted is not None:
            await self._publish_delta(f"{prefix}/audio/muted/state", "ON" if muted else "OFF")

        # PIP position + size
        pip_pos = await self._read(Commands.GET_PIP_POSITION, ResponseParser.parse_pip_position)
        if pip_pos is not None:
            pos_name = _PIP_POSITION_TO_NAME.get(pip_pos)
            if pos_name:
                await self._publish_delta(f"{prefix}/pip/position/state", pos_name)

        pip_sz = await self._read(Commands.GET_PIP_SIZE, ResponseParser.parse_pip_size)
        if pip_sz is not None:
            size_name = _PIP_SIZE_TO_NAME.get(pip_sz)
            if size_name:
                await self._publish_delta(f"{prefix}/pip/size/state", size_name)

        # Resolution
        res = await self._read(Commands.GET_OUTPUT_RES, ResponseParser.parse_resolution)
        if res is not None:
            await self._publish_delta(f"{prefix}/output/resolution/state", res)

    async def _read(self, command: str, parser):
        """Issue a serial command and parse the response. Returns None on
        any failure so the poller logs and moves on to the next group."""
        success, response, _ = await self.serial.send_command(command)
        if not success or response is None:
            return None
        try:
            return parser(response)
        except Exception as exc:
            log.warning("parse_failed", command=command, error=str(exc))
            return None

    async def _publish_delta(self, topic: str, value: str) -> None:
        """Publish only when the value has changed since the last cycle."""
        if self._last.get(topic) == value:
            return
        await self.mqtt.publish(topic, value, retain=True)
        self._last[topic] = value

    async def _publish_discovery(self) -> None:
        """Emit HA discovery payloads for every entity (retained)."""
        if not self.settings.ha_discovery_enabled:
            return

        prefix = self.settings.mqtt_topic_prefix.strip("/")
        availability_topic = self.mqtt.availability_topic
        device_id = self.settings.ha_device_id
        device_name = self.settings.ha_device_name
        discovery_prefix = self.settings.ha_discovery_prefix

        common: dict[str, Any] = {
            "discovery_prefix": discovery_prefix,
            "device_id": device_id,
            "device_name": device_name,
            "availability_topic": availability_topic,
            "model": self.settings.ha_device_model,
        }

        # switch.multiviewer_power
        topic, payload = power_switch_payload(
            **common,
            state_topic=f"{prefix}/power/state",
            command_topic=f"{prefix}/power/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        # binary_sensor.multiviewer_connected
        topic, payload = connected_binary_sensor_payload(
            **common,
            state_topic=f"{prefix}/connected/state",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        # select.multiviewer_mode
        topic, payload = mode_select_payload(
            **common,
            state_topic=f"{prefix}/mode/state",
            command_topic=f"{prefix}/mode/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        # select.multiviewer_window_{1..4}_input
        for n in range(1, 5):
            topic, payload = window_select_payload(
                n,
                **common,
                state_topic=f"{prefix}/windows/{n}/state",
                command_topic=f"{prefix}/windows/{n}/set",
            )
            await self.mqtt.publish(topic, payload, retain=True)

        # select.multiviewer_input_source
        topic, payload = input_source_select_payload(
            **common,
            state_topic=f"{prefix}/input/source/state",
            command_topic=f"{prefix}/input/source/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        # select.multiviewer_audio_source
        topic, payload = audio_source_select_payload(
            **common,
            state_topic=f"{prefix}/audio/source/state",
            command_topic=f"{prefix}/audio/source/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        # number.multiviewer_volume
        topic, payload = volume_number_payload(
            **common,
            state_topic=f"{prefix}/audio/volume/state",
            command_topic=f"{prefix}/audio/volume/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        # switch.multiviewer_muted (was binary_sensor; now writable)
        topic, payload = mute_switch_payload(
            **common,
            state_topic=f"{prefix}/audio/muted/state",
            command_topic=f"{prefix}/audio/muted/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        # select.multiviewer_pip_position
        topic, payload = pip_position_select_payload(
            **common,
            state_topic=f"{prefix}/pip/position/state",
            command_topic=f"{prefix}/pip/position/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        # select.multiviewer_pip_size
        topic, payload = pip_size_select_payload(
            **common,
            state_topic=f"{prefix}/pip/size/state",
            command_topic=f"{prefix}/pip/size/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        # sensor.multiviewer_resolution
        topic, payload = resolution_sensor_payload(
            **common,
            state_topic=f"{prefix}/output/resolution/state",
        )
        await self.mqtt.publish(topic, payload, retain=True)

        log.info("ha_discovery_published", device_id=device_id, entities=14)
