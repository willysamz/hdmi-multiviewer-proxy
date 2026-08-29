"""Targeted read-back after a set, and the sweep behaviour it must not disturb.

The characterization lists below were captured from the poller BEFORE the
refreshers were extracted, so they pin what a sweep publishes rather than
what the refactor happens to do. Two entries changed deliberately and are
marked; everything else is byte-identical to the pre-refactor sweep.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.controller import Controller
from app.poller import Poller
from app.serial_handler import ConnectionState

BORDER_COLORS_RESP = "\n".join(
    [
        "window 1 border color: red",
        "window 2 border color: blue",
        "window 3 border color: green",
        "window 4 border color: white",
    ]
)
ANSWERS = {
    "r power!": "power on",
    "r multiview!": "multiview: quad",
    "r window 1 in!": "window 1 in hdmi 1",
    "r window 2 in!": "window 2 in hdmi 2",
    "r window 3 in!": "window 3 in hdmi 3",
    "r window 4 in!": "window 4 in hdmi 4",
    "r in source!": "in source hdmi 2",
    "r output audio!": "output audio: hdmi 3",
    "r output audio vol!": "volume: 42",
    "r output audio mute!": "mute: off",
    "r pip position!": "PIP position: right bottom",
    "r pip size!": "PIP size: small",
    "r auto switch!": "auto switch on",
    "r input edid!": "input edid: 1080P 2CH",
    "r output res!": "output resolution: 1920x1080p60",
    "r output hdcp!": "output hdcp: hdcp 1.4",
    "r output vka!": "output vka: black screen",
    "r output itc!": "output itc: video mode",
    "r quad mode!": "quad mode 1",
    "r quad aspect!": "quad aspect: full screen",
    "r pbp mode!": "PBP mode 2",
    "r pbp aspect!": "PBP aspect: 16:9",
    "r triple mode!": "triple mode 1",
    "r triple aspect!": "triple aspect: full screen",
    "r window 0 border color!": BORDER_COLORS_RESP,
    "r window border!": "window border on",
    "r window source osd!": "window source osd on",
}


def _poller(profile_key="uhd401mv"):
    serial = MagicMock()
    serial.state = ConnectionState.ON
    serial.is_connected = True

    async def send(cmd):
        return (True, ANSWERS.get(cmd.strip().lower(), ""), None)

    serial.send_command = AsyncMock(side_effect=send)
    mqtt = MagicMock()
    mqtt.publish = AsyncMock()
    settings = MagicMock()
    settings.mqtt_topic_prefix = "mv"
    settings.ha_discovery_enabled = False
    settings.poll_interval = 10.0
    settings.device_profile = profile_key
    p = Poller(serial, mqtt, settings)
    p._discovery_published = True
    return p, serial, mqtt


def _published(mqtt):
    return [(c.args[0], c.args[1]) for c in mqtt.publish.call_args_list]


UHD_SLOW = [
    ("mv/connected/state", "ON"),
    ("mv/power/state", "ON"),
    ("mv/mode/state", "quad"),
    ("mv/windows/1/state", "HDMI 1"),
    ("mv/windows/2/state", "HDMI 2"),
    ("mv/windows/3/state", "HDMI 3"),
    ("mv/windows/4/state", "HDMI 4"),
    ("mv/input/source/state", "HDMI 2"),
    ("mv/audio/source/state", "HDMI 3"),
    ("mv/audio/volume/state", "42"),
    ("mv/audio/muted/state", "OFF"),
    ("mv/pip/position/state", "Bottom Right"),
    ("mv/pip/size/state", "Small"),
    ("mv/auto_switch/state", "ON"),
    ("mv/output/resolution/select/state", "1920x1080p60"),
    ("mv/output/resolution/state", "1920x1080p60"),
    ("mv/output/hdcp/state", "HDCP 1.4"),
    ("mv/output/vka/state", "Black screen"),
    ("mv/output/video_mode/state", "Video"),
    ("mv/quad/mode/state", "Mode 1"),
    ("mv/quad/aspect/state", "Full screen"),
    ("mv/pbp/mode/state", "Mode 2"),
    ("mv/pbp/aspect/state", "16:9"),
    ("mv/triple/mode/state", "Mode 1"),
    ("mv/triple/aspect/state", "Full screen"),
    ("mv/window/border/state", "ON"),
    ("mv/window/1/border_color/state", "red"),
    ("mv/window/2/border_color/state", "blue"),
    ("mv/window/3/border_color/state", "green"),
    ("mv/window/4/border_color/state", "white"),
    ("mv/window/source_osd/state", "ON"),
]

HDS_SLOW_TAIL = [
    ("mv/window/border/state", "ON"),  # HDS border is global: one topic
    ("mv/window/1/border_color/state", "red"),
    ("mv/window/2/border_color/state", "blue"),
    ("mv/window/3/border_color/state", "green"),
    ("mv/window/4/border_color/state", "white"),
    ("mv/window/source_osd/state", "ON"),
]


@pytest.mark.asyncio
async def test_uhd_slow_sweep_publishes_the_expected_set():
    p, _, mqtt = _poller("uhd401mv")
    p._cycle = 0  # cycle 1 is a slow boundary
    await p.poll_once()
    assert _published(mqtt) == UHD_SLOW


@pytest.mark.asyncio
async def test_fast_sweep_skips_the_config_class_group():
    """The slow group exists to keep idle polling off the serial line."""
    p, _, mqtt = _poller("uhd401mv")
    p._cycle = 1  # next cycle is 2 -- not a boundary
    await p.poll_once()
    topics = [t for t, _ in _published(mqtt)]
    for absent in (
        "mv/output/hdcp/state",
        "mv/quad/mode/state",
        "mv/window/source_osd/state",
        "mv/window/border/state",
    ):
        assert absent not in topics
    assert "mv/windows/1/state" in topics  # fast group still runs


@pytest.mark.asyncio
async def test_hds_border_is_global_not_per_window():
    p, _, mqtt = _poller("hds401mv")
    p._cycle = 0
    await p.poll_once()
    rows = _published(mqtt)
    assert rows[-len(HDS_SLOW_TAIL) :] == HDS_SLOW_TAIL
    assert not any(t.endswith("/border/state") and "/window/1/" in t for t, _ in rows)


@pytest.mark.asyncio
async def test_refresh_publishes_even_when_the_value_is_unchanged():
    """The device ignoring a write is the case that most needs a message.

    The HDS accepts EDID writes and does nothing. A delta-only publish stays
    silent, HA's optimistic toggle reverts, and the user sees the spring-back
    the read-back exists to remove.
    """
    p, _, mqtt = _poller("hds401mv")
    await p.refresh("source_osd")
    assert ("mv/window/source_osd/state", "ON") in _published(mqtt)
    mqtt.publish.reset_mock()
    await p.refresh("source_osd")  # same value again
    assert ("mv/window/source_osd/state", "ON") in _published(mqtt)


@pytest.mark.asyncio
async def test_refresh_is_gated_on_the_transport_not_the_cached_state():
    """A dead transport publishes nothing."""
    p, serial, mqtt = _poller("hds401mv")
    serial.is_connected = False
    await p.refresh("source_osd")
    assert _published(mqtt) == []


@pytest.mark.asyncio
async def test_refresh_works_while_the_cached_power_state_is_still_stale():
    """`serial.state` is only written by the 30s heartbeat.

    Gating the read-back on it meant that for up to a heartbeat after a
    power-on every set published nothing -- precisely when someone has just
    switched the unit on and is pressing buttons.
    """
    p, serial, mqtt = _poller("hds401mv")
    serial.state = ConnectionState.OFF  # heartbeat has not caught up yet
    serial.is_connected = True
    await p.refresh("source_osd")
    assert ("mv/window/source_osd/state", "ON") in _published(mqtt)


@pytest.mark.asyncio
async def test_unknown_refresh_key_raises():
    p, _, _ = _poller()
    for bad in ("nonsense", "layout:diagonal:mode", "layout:quad:sideways"):
        with pytest.raises(ValueError):
            await p.refresh(bad)


# (setter name, payload) covering every command the MQTT subscriber can route.
SETTERS = [
    ("set_mode", "quad"),
    ("set_input_source", "HDMI 3"),
    ("set_audio_source", "HDMI 2"),
    ("set_audio_volume", "40"),
    ("set_audio_mute", "ON"),
    ("set_pip_position", "Bottom Right"),
    ("set_pip_size", "Small"),
    ("set_auto_switch", "ON"),
    ("set_edid", None),  # payload filled from the profile's own option list
    ("set_output_resolution", None),
    ("set_hdcp", "HDCP 1.4"),
    ("set_vka", "Black screen"),
    ("set_video_mode", "Video"),
    ("set_quad_mode", "Mode 1"),
    ("set_quad_aspect", "16:9"),
    ("set_pbp_mode", "Mode 1"),
    ("set_pbp_aspect", "16:9"),
    ("set_triple_mode", "Mode 1"),
    ("set_triple_aspect", "16:9"),
    ("set_window_border", "ON"),
    ("set_source_osd", "ON"),
]


@pytest.mark.parametrize("profile_key", ["uhd401mv", "hds401mv"])
@pytest.mark.asyncio
async def test_every_setter_refreshes_a_key_that_resolves(profile_key):
    """Drive each setter for real rather than scraping keys out of the source.

    The previous version of this test regexed `refresh=` literals and then
    substituted the *placeholder names* (`{layout}` -> "quad"), so the only
    layout key it ever resolved was the one that happened to work. It passed
    while `set_pbp_mode` raised ValueError on every call, because "PBP mode"
    lowercases to a key the layout table does not hold -- and that exception
    also skipped the nudge, sending PBP entities back to 60s confirmation.
    """
    from app.controller import ControllerError

    for name, payload in SETTERS:
        c, p, serial, _ = _controller(profile_key)
        if payload is None:
            options = p.profile.edid_options if name == "set_edid" else p.profile.resolution_options
            payload = options[0]
        keys = []
        p.refresh = AsyncMock(side_effect=lambda k: keys.append(k))
        nudges = []
        p.trigger_immediate_poll = MagicMock(side_effect=lambda: nudges.append(1))
        try:
            await getattr(c, name)(payload)
        except ControllerError:
            continue  # this profile genuinely lacks the command
        assert keys, f"{name} sent no refresh key"
        p._resolve_refresh(keys[0])  # raises if the key is not a real refresher
        assert nudges, f"{name} did not nudge the sweep"


@pytest.mark.asyncio
async def test_a_broken_refresh_still_nudges_the_sweep():
    """The nudge is the fallback. It must survive anything the refresh does."""
    c, p, serial, _ = _controller("hds401mv")
    p.refresh = AsyncMock(side_effect=ValueError("unknown refresh key"))
    nudges = []
    p.trigger_immediate_poll = MagicMock(side_effect=lambda: nudges.append(1))
    await c.set_source_osd("OFF")  # must not raise
    assert nudges, "a failing read-back cancelled the sweep nudge"


@pytest.mark.asyncio
async def test_a_command_supersedes_an_in_flight_sweeps_publishes():
    """The race the read-back would otherwise introduce.

    The sweep runs on the poller task and the command on the subscriber task.
    A sweep holding reads taken BEFORE the command must not publish them
    afterwards, or the entity shows the new value, snaps back to the old one,
    and corrects a sweep later -- a visible flicker.
    """
    p, _, mqtt = _poller("uhd401mv")
    gen = p._generation
    await p._publish_delta("mv/mode/state", "quad", gen=gen)
    assert ("mv/mode/state", "quad") in _published(mqtt)

    mqtt.publish.reset_mock()
    p.trigger_immediate_poll()  # a command lands
    await p._publish_delta("mv/mode/state", "pbp", gen=gen)  # sweep's stale read
    assert _published(mqtt) == []


@pytest.mark.asyncio
async def test_publish_cache_rolls_back_when_the_broker_rejects():
    p, _, mqtt = _poller()
    mqtt.publish = AsyncMock(side_effect=RuntimeError("broker down"))
    with pytest.raises(RuntimeError):
        await p._publish_delta("mv/mode/state", "quad")
    assert p._last.get("mv/mode/state") is None
    mqtt.publish = AsyncMock()
    await p._publish_delta("mv/mode/state", "quad")  # must not be suppressed
    assert _published(mqtt) == [("mv/mode/state", "quad")]


def _controller(profile_key="hds401mv"):
    p, serial, mqtt = _poller(profile_key)
    settings = p.settings
    c = Controller(serial=serial, mqtt=mqtt, poller=p, settings=settings)
    return c, p, serial, mqtt


@pytest.mark.asyncio
async def test_set_reads_back_before_nudging_the_sweep():
    c, p, serial, mqtt = _controller("hds401mv")
    order = []
    p.refresh = AsyncMock(side_effect=lambda k: order.append(f"refresh:{k}"))
    p.trigger_immediate_poll = MagicMock(side_effect=lambda: order.append("nudge"))
    await c.set_source_osd("OFF")
    assert order == ["refresh:source_osd", "nudge"]


@pytest.mark.asyncio
async def test_a_failed_read_back_does_not_fail_a_command_that_succeeded():
    c, p, serial, mqtt = _controller("hds401mv")
    p.refresh = AsyncMock(side_effect=TimeoutError("read timed out"))
    await c.set_source_osd("OFF")  # must not raise
    assert serial.send_command.await_args_list[0].args[0] == "s window source osd 0!"


@pytest.mark.asyncio
async def test_refresh_supersedes_the_sweep_before_it_publishes():
    """Ordering, not just existence, of the generation bump.

    A sweep that has already passed its generation check is sitting between
    its own read and its publish. If the bump happened after the read-back
    published, that stale publish would land on top of the fresh value and
    the entity would spring back anyway -- the bug, reintroduced one await
    later. The bump must precede the read-back's publish.
    """
    p, _, mqtt = _poller("hds401mv")
    before = p._generation
    seen = {}

    async def capture(topic, value, retain=True):
        seen["gen_at_publish"] = p._generation

    mqtt.publish = AsyncMock(side_effect=capture)
    await p.refresh("source_osd")
    assert seen["gen_at_publish"] != before


@pytest.mark.asyncio
async def test_a_set_during_a_sweep_wins_end_to_end():
    """Full path: sweep running on one task, a set on another.

    Exercises poll_once and Controller.set_* together rather than calling
    _publish_delta by hand, so it covers the bump ordering, the sweep's
    abandonment, and the read-back's forced publish as one behaviour.
    """
    p, serial, mqtt = _poller("hds401mv")
    current = {"osd": "on"}

    async def send(cmd):
        c = cmd.strip().lower()
        await asyncio.sleep(0.005)  # every round trip costs time
        if c == "s window source osd 0!":
            current["osd"] = "off"
            return (True, "ok", None)
        if c == "r window source osd!":
            return (True, f"window source osd {current['osd']}", None)
        return (True, ANSWERS.get(c, ""), None)

    serial.send_command = AsyncMock(side_effect=send)
    c = Controller(serial=serial, mqtt=mqtt, poller=p, settings=p.settings)

    p._cycle = 0  # a slow sweep, so source_osd is in it
    sweep = asyncio.create_task(p.poll_once())
    await asyncio.sleep(0.02)  # let the sweep get under way
    await c.set_source_osd("OFF")
    await sweep

    osd = [v for t, v in _published(mqtt) if t == "mv/window/source_osd/state"]
    assert osd, "source OSD was never published"
    assert osd[-1] == "OFF", f"sweep overwrote the read-back: {osd}"
