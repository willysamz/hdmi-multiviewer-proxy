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
    ResponseParser,
)
from app.discovery import (
    audio_source_select_payload,
    auto_switch_switch_payload,
    border_color_select_payload,
    connected_binary_sensor_payload,
    edid_select_payload,
    edid_sensor_payload,
    hdcp_select_payload,
    input_source_select_payload,
    layout_select_payload,
    mode_select_payload,
    mute_switch_payload,
    pip_position_select_payload,
    pip_size_select_payload,
    power_switch_payload,
    reboot_button_payload,
    resolution_select_payload,
    resolution_sensor_payload,
    source_osd_switch_payload,
    video_mode_select_payload,
    vka_select_payload,
    volume_number_payload,
    window_border_per_window_switch_payload,
    window_border_switch_payload,
    window_select_payload,
)
from app.profiles import (
    ASPECT_OPTIONS,
    BORDER_COLORS,
    CAP_AUTO_SWITCH,
    CAP_EDID,
    CAP_HDCP,
    CAP_ITC,
    CAP_SOURCE_OSD,
    CAP_VKA,
    CAP_VOLUME,
    CAP_WINDOW_BORDER,
    HDCP_OPTIONS,
    LAYOUT_MODE_OPTIONS,
    VIDEO_MODE_OPTIONS,
    VKA_OPTIONS,
    get_profile,
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
        self.profile = get_profile(settings.device_profile)

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._immediate_event = asyncio.Event()

        self._discovery_published = False
        # Config-class settings (HDCP, VKA, ITC, layout aspects, border
        # colours) barely ever change, and reading them every cycle would
        # roughly double the serial traffic on a 115200 line for no benefit.
        # They are refreshed every SLOW_POLL_EVERY cycles instead.
        self._cycle = 0
        # Set by trigger_immediate_poll so the nudged cycle reads the
        # config-class group too. Consumed at the top of poll_once.
        self._force_slow = False
        # Bumped by every command. A sweep stamps its publishes with the value
        # current when it started, so reads taken before a command can never
        # overwrite what that command's read-back published.
        self._generation = 0
        # Per-topic last-published cache so we publish deltas only.
        self._last: dict[str, str] = {}

    def trigger_immediate_poll(self) -> None:
        """Poll right now, reading every group including the config-class one.

        A command can change any entity, and roughly a third of them live in
        the slow group. Nudging without forcing `slow` left those confirming
        only at the next SLOW_POLL_EVERY boundary -- up to a minute later --
        during which HA kept showing the pre-command value and the toggle
        appeared to spring back.
        """
        self._force_slow = True
        self._generation += 1
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
            # Cleared before the poll, never after: a command landing while
            # poll_once is in flight would otherwise have its nudge wiped and
            # wait a full poll_interval for confirmation.
            self._immediate_event.clear()
            try:
                await self.poll_once()
            except Exception as exc:
                log.warning("poll_cycle_failed", error=str(exc))

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

    SLOW_POLL_EVERY = 6

    async def poll_once(self) -> None:
        """One cycle: query each entity group + publish deltas."""
        self._cycle += 1
        slow = self._force_slow or self._cycle == 1 or self._cycle % self.SLOW_POLL_EVERY == 0
        self._force_slow = False
        # A command handled on the subscriber task publishes the setting it
        # changed straight away. This sweep runs on the poller task and may
        # already hold reads taken BEFORE that command, so anything it
        # publishes afterwards would be stale and overwrite the fresh value --
        # the entity would show the new value, snap back, then correct on the
        # next sweep. Every publish below is stamped with the generation
        # current at entry and dropped once a command supersedes it.
        gen = self._generation

        # Always publish discovery on first cycle (even if some queries fail).
        if not self._discovery_published:
            await self._publish_discovery()
            self._discovery_published = True

        prefix = self.settings.mqtt_topic_prefix.strip("/")

        # Connectivity: derived from the serial handler's state property.
        connected = self.serial.state == ConnectionState.ON
        await self._publish_delta(
            f"{prefix}/connected/state", "ON" if connected else "OFF", gen=gen
        )

        # Power comes from the device's own `r power!` answer, and ONLY from
        # that. The read is gated on the LIVE transport status (is_connected)
        # rather than the cached `state`, which only updates at connect and on
        # the 30s heartbeat and would otherwise republish a stale value.
        power = None
        if self.serial.is_connected:
            power = await self._read(self.profile.GET_POWER, ResponseParser.parse_power)
        if power is not None:
            await self._publish_delta(f"{prefix}/power/state", "ON" if power else "OFF", gen=gen)
        elif not self.serial.is_connected:
            # Transport is down: report OFF. Deliberate fail-safe so automations
            # that gate on power never act on a device we cannot reach.
            await self._publish_delta(f"{prefix}/power/state", "OFF", gen=gen)
        # Remaining case: the socket claims to be open but the read failed, so
        # we do NOT know the power state -- publish nothing and let the last
        # value stand. This branch used to assume "socket up -> ON". On
        # 2026-08-28 a USB/IP re-attach left pyserial's is_open True on a dead
        # handle while every read returned empty, and HA was told the unit was
        # ON for minutes while nothing could be read from it. `connected/state`
        # above already carries the real signal.

        # The remaining queries only work when the device is powered ON.
        if not connected:
            return

        # From here on, bail out as soon as a command supersedes this sweep:
        # its remaining reads would contend with that command's own traffic on
        # the serial line and then be dropped at publish time anyway.
        if gen != self._generation:
            return
        await self.refresh_mode(gen=gen)
        for n in range(1, 5):
            await self.refresh_window(n, gen=gen)
        if gen != self._generation:
            return
        await self.refresh_input_source(gen=gen)
        await self.refresh_audio_source(gen=gen)
        await self.refresh_audio_volume(gen=gen)
        await self.refresh_audio_muted(gen=gen)
        await self.refresh_pip_position(gen=gen)
        await self.refresh_pip_size(gen=gen)
        if gen != self._generation:
            return
        await self.refresh_auto_switch(gen=gen)
        await self.refresh_edid(gen=gen)
        await self.refresh_resolution(gen=gen)

        if slow:
            await self._poll_config_settings(gen=gen)

    async def _poll_config_settings(self, *, gen: int | None = None) -> None:
        """Read the rarely-changing settings. Runs every SLOW_POLL_EVERY cycles.

        Reading these every cycle would roughly double the serial traffic on a
        115200 line for no benefit, so the sweep visits them on a boundary --
        or whenever a command forces it.
        """
        if gen is not None and gen != self._generation:
            return
        await self.refresh_hdcp(gen=gen)
        await self.refresh_vka(gen=gen)
        await self.refresh_video_mode(gen=gen)
        for layout in ("quad", "pbp", "triple"):
            if gen is not None and gen != self._generation:
                return
            await self.refresh_layout_mode(layout, gen=gen)
            await self.refresh_layout_aspect(layout, gen=gen)
        if gen is not None and gen != self._generation:
            return
        await self.refresh_window_border(gen=gen)
        await self.refresh_border_colors(gen=gen)
        await self.refresh_source_osd(gen=gen)

    # ---- per-setting refreshers ------------------------------------------
    #
    # Each reads ONE setting and publishes its topic(s). The sweep above walks
    # them in order; Controller._send calls the single one its command changed
    # so a set confirms in one round trip instead of waiting out the sweep.
    # Each setting's command, value mapping and topic therefore live in one
    # place on the MQTT path. (The REST routers are a separate path: they call
    # the serial handler directly with the legacy Commands class and publish
    # nothing.)
    #
    # `force` bypasses the change-detection cache. After a command HA needs a
    # message even when the value is unchanged -- that is exactly the case
    # where the device IGNORED the write, and silence there would leave HA's
    # optimistic toggle to revert with no correction.

    @property
    def _prefix(self) -> str:
        return self.settings.mqtt_topic_prefix.strip("/")

    async def refresh_mode(self, *, gen: int | None = None, force: bool = False) -> None:
        mode = await self._read(self.profile.GET_MULTIVIEW, ResponseParser.parse_multiview_mode)
        if mode is not None:
            await self._publish_delta(f"{self._prefix}/mode/state", mode, gen=gen, force=force)

    async def refresh_window(
        self, window_n: int, *, gen: int | None = None, force: bool = False
    ) -> None:
        cmd = self.profile.GET_WINDOW_INPUT.format(x=window_n)
        window_in = await self._read(cmd, ResponseParser.parse_window_input)
        if window_in is not None:
            await self._publish_delta(
                f"{self._prefix}/windows/{window_n}/state",
                f"HDMI {window_in}",
                gen=gen,
                force=force,
            )

    async def refresh_input_source(self, *, gen: int | None = None, force: bool = False) -> None:
        in_src = await self._read(self.profile.GET_INPUT_SOURCE, ResponseParser.parse_input_source)
        if in_src is not None:
            await self._publish_delta(
                f"{self._prefix}/input/source/state", f"HDMI {in_src}", gen=gen, force=force
            )

    async def refresh_audio_source(self, *, gen: int | None = None, force: bool = False) -> None:
        audio_src = await self._read(
            self.profile.GET_AUDIO_SOURCE, ResponseParser.parse_audio_source
        )
        if audio_src is not None:
            name = _AUDIO_SOURCE_CODE_TO_NAME.get(audio_src, f"HDMI {audio_src}")
            await self._publish_delta(
                f"{self._prefix}/audio/source/state", name, gen=gen, force=force
            )

    async def refresh_audio_volume(self, *, gen: int | None = None, force: bool = False) -> None:
        if not self.profile.supports(CAP_VOLUME):
            return
        vol = await self._read(self.profile.GET_AUDIO_VOL, ResponseParser.parse_volume)
        if vol is not None:
            await self._publish_delta(
                f"{self._prefix}/audio/volume/state", str(vol), gen=gen, force=force
            )

    async def refresh_audio_muted(self, *, gen: int | None = None, force: bool = False) -> None:
        muted = await self._read(self.profile.GET_AUDIO_MUTE, ResponseParser.parse_mute)
        if muted is not None:
            await self._publish_delta(
                f"{self._prefix}/audio/muted/state", "ON" if muted else "OFF", gen=gen, force=force
            )

    async def refresh_pip_position(self, *, gen: int | None = None, force: bool = False) -> None:
        pip_pos = await self._read(self.profile.GET_PIP_POSITION, ResponseParser.parse_pip_position)
        if pip_pos is not None:
            pos_name = _PIP_POSITION_TO_NAME.get(pip_pos)
            if pos_name:
                await self._publish_delta(
                    f"{self._prefix}/pip/position/state", pos_name, gen=gen, force=force
                )

    async def refresh_pip_size(self, *, gen: int | None = None, force: bool = False) -> None:
        pip_sz = await self._read(self.profile.GET_PIP_SIZE, ResponseParser.parse_pip_size)
        if pip_sz is not None:
            size_name = _PIP_SIZE_TO_NAME.get(pip_sz)
            if size_name:
                await self._publish_delta(
                    f"{self._prefix}/pip/size/state", size_name, gen=gen, force=force
                )

    async def refresh_auto_switch(self, *, gen: int | None = None, force: bool = False) -> None:
        if not self.profile.supports(CAP_AUTO_SWITCH):
            return
        auto = await self._read(self.profile.GET_AUTO_SWITCH, ResponseParser.parse_auto_switch)
        if auto is not None:
            await self._publish_delta(
                f"{self._prefix}/auto_switch/state", "ON" if auto else "OFF", gen=gen, force=force
            )

    async def refresh_edid(self, *, gen: int | None = None, force: bool = False) -> None:
        """One read, but one of TWO topics.

        Publish only a value the select actually offers: HA rejects a state
        absent from options[] and logs an error every time -- and the HDS
        reports real mode NAMES (`copy from hdmi out`) while its option list is
        still generic, so an unguarded publish would error on every poll. When
        the labels are unverified the real value goes to the diagnostic sensor
        instead of being discarded.
        """
        if not self.profile.supports(CAP_EDID):
            return
        edid = await self._read(self.profile.GET_INPUT_EDID, ResponseParser.parse_edid)
        if edid is None:
            return
        if self.profile.edid_options_verified:
            match = next(
                (o for o in self.profile.edid_options if o.lower() == edid.strip().lower()),
                None,
            )
            if match:
                await self._publish_delta(f"{self._prefix}/edid/state", match, gen=gen, force=force)
        else:
            await self._publish_delta(f"{self._prefix}/edid/mode/state", edid, gen=gen, force=force)

    async def refresh_resolution(self, *, gen: int | None = None, force: bool = False) -> None:
        """One read, TWO topics: the select and the raw diagnostic sensor.

        The select can only offer settable values; the device may report AUTO,
        which is not one of them. Publish the select's state only when it maps
        to an option, so HA never shows an invalid state -- the sensor always
        carries the verbatim value.
        """
        res = await self._read(self.profile.GET_OUTPUT_RES, ResponseParser.parse_resolution)
        if res is None:
            return
        if self.profile.resolution_options:
            match = next(
                (o for o in self.profile.resolution_options if o.lower() == res.strip().lower()),
                None,
            )
            if match:
                await self._publish_delta(
                    f"{self._prefix}/output/resolution/select/state", match, gen=gen, force=force
                )
        await self._publish_delta(
            f"{self._prefix}/output/resolution/state", res, gen=gen, force=force
        )

    async def refresh_hdcp(self, *, gen: int | None = None, force: bool = False) -> None:
        if not self.profile.supports(CAP_HDCP):
            return
        v = await self._read(self.profile.GET_OUTPUT_HDCP, ResponseParser.parse_hdcp)
        name = {"hdcp_1_4": "HDCP 1.4", "hdcp_2_2": "HDCP 2.2", "off": "Off"}.get(v or "")
        if name:
            await self._publish_delta(
                f"{self._prefix}/output/hdcp/state", name, gen=gen, force=force
            )

    async def refresh_vka(self, *, gen: int | None = None, force: bool = False) -> None:
        if not self.profile.supports(CAP_VKA):
            return
        v = await self._read(self.profile.GET_OUTPUT_VKA, ResponseParser.parse_vka)
        name = {"black_screen": "Black screen", "blue_screen": "Blue screen"}.get(v or "")
        if name:
            await self._publish_delta(
                f"{self._prefix}/output/vka/state", name, gen=gen, force=force
            )

    async def refresh_video_mode(self, *, gen: int | None = None, force: bool = False) -> None:
        if not self.profile.supports(CAP_ITC):
            return
        v = await self._read(self.profile.GET_OUTPUT_ITC, ResponseParser.parse_video_mode)
        name = {"video": "Video", "pc": "PC"}.get(v or "")
        if name:
            await self._publish_delta(
                f"{self._prefix}/output/video_mode/state", name, gen=gen, force=force
            )

    _LAYOUT_COMMANDS = {
        "quad": ("GET_QUAD_MODE", "GET_QUAD_ASPECT"),
        "pbp": ("GET_PBP_MODE", "GET_PBP_ASPECT"),
        "triple": ("GET_TRIPLE_MODE", "GET_TRIPLE_ASPECT"),
    }

    async def refresh_layout_mode(
        self, layout: str, *, gen: int | None = None, force: bool = False
    ) -> None:
        cmd = getattr(self.profile, self._LAYOUT_COMMANDS[layout][0])
        m = await self._read(cmd, ResponseParser.parse_pbp_mode)
        if m in (1, 2):
            await self._publish_delta(
                f"{self._prefix}/{layout}/mode/state",
                LAYOUT_MODE_OPTIONS[m - 1],
                gen=gen,
                force=force,
            )

    async def refresh_layout_aspect(
        self, layout: str, *, gen: int | None = None, force: bool = False
    ) -> None:
        cmd = getattr(self.profile, self._LAYOUT_COMMANDS[layout][1])
        a = await self._read(cmd, ResponseParser.parse_aspect)
        name = {"full_screen": ASPECT_OPTIONS[0], "16_9": ASPECT_OPTIONS[1]}.get(a or "")
        if name:
            await self._publish_delta(
                f"{self._prefix}/{layout}/aspect/state", name, gen=gen, force=force
            )

    async def refresh_window_border(self, *, gen: int | None = None, force: bool = False) -> None:
        """Border on/off, from the global `r window border!`.

        KNOWN GAP, deliberately not fixed here: the UHD sets borders per window
        and discovery gives it four switches on `window/{n}/border/state`, which
        nothing publishes -- so those four never receive state at all. The
        obvious fix is `GET_ALL_WINDOW_BORDERS` with `parse_window_borders`, but
        that parser's own docstring records that the UHD's reply format has
        never been captured, and the unit was powered off when this was written.
        Shipping a guess would either publish nothing (no better) or spend a
        full serial timeout per sweep on a command the UHD may not answer.
        Capture the real reply on the powered-on UHD first.
        """
        if not self.profile.supports(CAP_WINDOW_BORDER):
            return
        b = await self._read(self.profile.GET_WINDOW_BORDER, ResponseParser.parse_window_border)
        if b is not None:
            await self._publish_delta(
                f"{self._prefix}/window/border/state", "ON" if b else "OFF", gen=gen, force=force
            )

    async def refresh_border_colors(self, *, gen: int | None = None, force: bool = False) -> None:
        """One read, up to FOUR topics -- `r window 0 border color!` answers
        for every window, so a change to one still refreshes all four."""
        if not self.profile.supports(CAP_WINDOW_BORDER):
            return
        colors = await self._read(
            self.profile.GET_ALL_WINDOW_BORDER_COLORS, ResponseParser.parse_border_colors
        )
        for n, name in (colors or {}).items():
            if name in BORDER_COLORS:
                await self._publish_delta(
                    f"{self._prefix}/window/{n}/border_color/state", name, gen=gen, force=force
                )

    async def refresh_source_osd(self, *, gen: int | None = None, force: bool = False) -> None:
        if not self.profile.supports(CAP_SOURCE_OSD):
            return
        v = await self._read(self.profile.GET_SOURCE_OSD, ResponseParser.parse_source_osd)
        if v is not None:
            await self._publish_delta(
                f"{self._prefix}/window/source_osd/state",
                "ON" if v else "OFF",
                gen=gen,
                force=force,
            )

    async def refresh(self, key: str) -> None:
        """Read+publish the single setting `key` names, forcing the publish.

        Called by Controller._send straight after a successful write. Raises
        on an unknown key -- but note _send catches that and logs it, because
        a command that already succeeded must not be reported as failed and
        the sweep nudge must still fire. So the real guard against a typo is
        the test that resolves every key each setter emits, not this raise.
        """
        target, arg = self._resolve_refresh(key)
        # Supersede any sweep in flight BEFORE publishing, not after. A sweep
        # sitting between its own read and its publish has already passed its
        # generation check, so bumping afterwards would let its stale value
        # land on top of the value we are about to publish.
        self._generation += 1
        # Gate on the LIVE transport, not `serial.state`: that is written only
        # by the heartbeat, so for up to heartbeat_interval after a power-on it
        # still reads OFF -- and every read-back in that window would publish
        # nothing, exactly when someone is most likely pressing buttons. A read
        # against a powered-off device simply returns None and publishes
        # nothing, so this gate only has to exclude a dead transport.
        if not self.serial.is_connected:
            return
        if arg is None:
            await target(force=True)
        else:
            await target(arg, force=True)

    def _resolve_refresh(self, key: str) -> tuple[Any, Any]:
        """Map a refresh key to its bound refresher and optional argument."""
        if key.startswith("window:"):
            return self.refresh_window, int(key.split(":", 1)[1])
        if key.startswith("layout:"):
            _, layout, kind = key.split(":")
            if layout not in self._LAYOUT_COMMANDS:
                raise ValueError(f"unknown layout in refresh key: {key!r}")
            if kind == "mode":
                return self.refresh_layout_mode, layout
            if kind == "aspect":
                return self.refresh_layout_aspect, layout
            raise ValueError(f"unknown layout kind in refresh key: {key!r}")
        simple = {
            "mode": self.refresh_mode,
            "input_source": self.refresh_input_source,
            "audio_source": self.refresh_audio_source,
            "audio_volume": self.refresh_audio_volume,
            "audio_muted": self.refresh_audio_muted,
            "pip_position": self.refresh_pip_position,
            "pip_size": self.refresh_pip_size,
            "auto_switch": self.refresh_auto_switch,
            "edid": self.refresh_edid,
            "resolution": self.refresh_resolution,
            "hdcp": self.refresh_hdcp,
            "vka": self.refresh_vka,
            "video_mode": self.refresh_video_mode,
            "window_border": self.refresh_window_border,
            "border_colors": self.refresh_border_colors,
            "source_osd": self.refresh_source_osd,
        }
        if key not in simple:
            raise ValueError(f"unknown refresh key: {key!r}")
        return simple[key], None

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

    async def _publish_delta(
        self, topic: str, value: str, *, gen: int | None = None, force: bool = False
    ) -> None:
        """Publish when the value changed -- or unconditionally when forced.

        `gen` stamps a sweep's publishes: once a command bumps the generation
        the sweep's remaining reads are older than the command and must not
        overwrite what the command's own read-back published.

        The cache is written BEFORE the await, not after: with two tasks
        publishing, a check-then-await-then-assign guard can be interleaved.
        It is rolled back if the publish fails, so a dropped message never
        suppresses a later retry of the same value.
        """
        if gen is not None and gen != self._generation:
            return
        if not force and self._last.get(topic) == value:
            return
        previous = self._last.get(topic)
        self._last[topic] = value
        try:
            await self.mqtt.publish(topic, value, retain=True)
        except Exception:
            # Only roll back if nothing else published this topic meanwhile,
            # so a concurrent publisher's value is never overwritten by a
            # stale snapshot.
            if self._last.get(topic) == value:
                if previous is None:
                    self._last.pop(topic, None)
                else:
                    self._last[topic] = previous
            raise

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

        # Counted rather than hardcoded: the entity set now varies by profile.
        published = 0
        retracted = 0

        # switch.multiviewer_power
        topic, payload = power_switch_payload(
            **common,
            state_topic=f"{prefix}/power/state",
            command_topic=f"{prefix}/power/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        # binary_sensor.multiviewer_connected
        topic, payload = connected_binary_sensor_payload(
            **common,
            state_topic=f"{prefix}/connected/state",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        # select.multiviewer_mode
        topic, payload = mode_select_payload(
            **common,
            state_topic=f"{prefix}/mode/state",
            command_topic=f"{prefix}/mode/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        # select.multiviewer_window_{1..4}_input
        for n in range(1, 5):
            topic, payload = window_select_payload(
                n,
                **common,
                state_topic=f"{prefix}/windows/{n}/state",
                command_topic=f"{prefix}/windows/{n}/set",
            )
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1

        # select.multiviewer_input_source
        topic, payload = input_source_select_payload(
            **common,
            state_topic=f"{prefix}/input/source/state",
            command_topic=f"{prefix}/input/source/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        # select.multiviewer_audio_source
        topic, payload = audio_source_select_payload(
            **common,
            state_topic=f"{prefix}/audio/source/state",
            command_topic=f"{prefix}/audio/source/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        # number.multiviewer_volume -- UHD only. The HDS has no volume command
        # at all; publishing this against one produces a control that cannot
        # work and makes the poller emit `E00` every cycle. If the capability
        # is absent we publish an EMPTY retained payload to the same config
        # topic, which is how HA deletes a previously-discovered entity --
        # otherwise a phantom entity survives forever from an earlier release.
        topic, payload = volume_number_payload(
            **common,
            state_topic=f"{prefix}/audio/volume/state",
            command_topic=f"{prefix}/audio/volume/set",
        )
        if self.profile.supports(CAP_VOLUME):
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1
        else:
            await self.mqtt.publish(topic, "", retain=True)
            retracted += 1

        # switch.multiviewer_muted (was binary_sensor; now writable)
        topic, payload = mute_switch_payload(
            **common,
            state_topic=f"{prefix}/audio/muted/state",
            command_topic=f"{prefix}/audio/muted/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        # select.multiviewer_pip_position
        topic, payload = pip_position_select_payload(
            **common,
            options=list(self.profile.pip_position_options),
            state_topic=f"{prefix}/pip/position/state",
            command_topic=f"{prefix}/pip/position/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        # select.multiviewer_pip_size
        topic, payload = pip_size_select_payload(
            **common,
            options=list(self.profile.pip_size_options),
            state_topic=f"{prefix}/pip/size/state",
            command_topic=f"{prefix}/pip/size/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        # switch.multiviewer_auto_switch
        if self.profile.supports(CAP_AUTO_SWITCH):
            topic, payload = auto_switch_switch_payload(
                **common,
                state_topic=f"{prefix}/auto_switch/state",
                command_topic=f"{prefix}/auto_switch/set",
            )
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1

        # select.multiviewer_edid -- options come from the profile; the models
        # expose different mode counts and their labels are not interchangeable.
        if self.profile.supports(CAP_EDID):
            topic, payload = edid_select_payload(
                **common,
                options=list(self.profile.edid_options),
                state_topic=f"{prefix}/edid/state",
                command_topic=f"{prefix}/edid/set",
            )
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1

        # --- Phase 5: full command exposure ---

        if self.profile.resolution_options:
            topic, payload = resolution_select_payload(
                **common,
                options=list(self.profile.resolution_options),
                state_topic=f"{prefix}/output/resolution/select/state",
                command_topic=f"{prefix}/output/resolution/set",
            )
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1

        if self.profile.supports(CAP_HDCP):
            topic, payload = hdcp_select_payload(
                **common,
                options=list(HDCP_OPTIONS),
                state_topic=f"{prefix}/output/hdcp/state",
                command_topic=f"{prefix}/output/hdcp/set",
            )
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1

        if self.profile.supports(CAP_VKA):
            topic, payload = vka_select_payload(
                **common,
                options=list(VKA_OPTIONS),
                state_topic=f"{prefix}/output/vka/state",
                command_topic=f"{prefix}/output/vka/set",
            )
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1

        if self.profile.supports(CAP_ITC):
            topic, payload = video_mode_select_payload(
                **common,
                options=list(VIDEO_MODE_OPTIONS),
                state_topic=f"{prefix}/output/video_mode/state",
                command_topic=f"{prefix}/output/video_mode/set",
            )
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1

        for layout in ("quad", "pbp", "triple"):
            for kind, opts in (
                (
                    "mode",
                    self.profile.quad_mode_options if layout == "quad" else LAYOUT_MODE_OPTIONS,
                ),
                ("aspect", ASPECT_OPTIONS),
            ):
                topic, payload = layout_select_payload(
                    **common,
                    layout=layout,
                    kind=kind,
                    options=list(opts),
                    state_topic=f"{prefix}/{layout}/{kind}/state",
                    command_topic=f"{prefix}/{layout}/{kind}/set",
                )
                await self.mqtt.publish(topic, payload, retain=True)
                published += 1

        if self.profile.supports(CAP_EDID) and not self.profile.edid_options_verified:
            topic, payload = edid_sensor_payload(
                **common,
                state_topic=f"{prefix}/edid/mode/state",
            )
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1

        if self.profile.supports(CAP_WINDOW_BORDER):
            if self.profile.border_scope == "window":
                for n in range(1, 5):
                    topic, payload = window_border_per_window_switch_payload(
                        n,
                        **common,
                        state_topic=f"{prefix}/window/{n}/border/state",
                        command_topic=f"{prefix}/window/{n}/border/set",
                    )
                    await self.mqtt.publish(topic, payload, retain=True)
                    published += 1
            else:
                topic, payload = window_border_switch_payload(
                    **common,
                    state_topic=f"{prefix}/window/border/state",
                    command_topic=f"{prefix}/window/border/set",
                )
                await self.mqtt.publish(topic, payload, retain=True)
                published += 1
            for n in range(1, 5):
                topic, payload = border_color_select_payload(
                    n,
                    **common,
                    options=list(BORDER_COLORS),
                    state_topic=f"{prefix}/window/{n}/border_color/state",
                    command_topic=f"{prefix}/window/{n}/border_color/set",
                )
                await self.mqtt.publish(topic, payload, retain=True)
                published += 1

        if self.profile.supports(CAP_SOURCE_OSD):
            topic, payload = source_osd_switch_payload(
                **common,
                state_topic=f"{prefix}/window/source_osd/state",
                command_topic=f"{prefix}/window/source_osd/set",
            )
            await self.mqtt.publish(topic, payload, retain=True)
            published += 1

        topic, payload = reboot_button_payload(
            discovery_prefix=discovery_prefix,
            device_id=device_id,
            device_name=device_name,
            availability_topic=availability_topic,
            model=self.settings.ha_device_model,
            command_topic=f"{prefix}/reboot/set",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        # sensor.multiviewer_resolution
        topic, payload = resolution_sensor_payload(
            **common,
            state_topic=f"{prefix}/output/resolution/state",
        )
        await self.mqtt.publish(topic, payload, retain=True)
        published += 1

        log.info(
            "ha_discovery_published",
            device_id=device_id,
            profile=self.profile.key,
            entities=published,
            retracted=retracted,
        )
