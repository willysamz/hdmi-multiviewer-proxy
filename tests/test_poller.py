import pytest
from unittest.mock import AsyncMock, MagicMock
from app.poller import Poller
from app.serial_handler import ConnectionState


def _poller():
    serial = MagicMock()
    serial.state = ConnectionState.ON
    serial.is_connected = True
    mqtt = MagicMock()
    mqtt.publish = AsyncMock()
    settings = MagicMock()
    settings.mqtt_topic_prefix = "mv"
    settings.ha_discovery_enabled = False
    settings.poll_interval = 10.0
    settings.device_profile = "uhd401mv"
    p = Poller(serial, mqtt, settings)
    p._discovery_published = True  # skip discovery in these tests
    return p, serial, mqtt


@pytest.mark.asyncio
async def test_power_state_reads_device_not_connection():
    p, serial, mqtt = _poller()
    serial.state = ConnectionState.ON
    serial.is_connected = True
    # Device answers "power off" even though the socket is up.
    serial.send_command = AsyncMock(return_value=(True, "power off", None))
    await p.poll_once()
    published = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    assert published["mv/power/state"] == "OFF"


@pytest.mark.asyncio
async def test_power_is_not_invented_when_the_socket_lies():
    """Socket open + read failed => we do NOT know the power state.

    This previously published "ON" on the reasoning "socket up -> assume on".
    A USB/IP re-attach on 2026-08-28 disproved that: pyserial's is_open stayed
    True on a dead handle while every read returned empty, and HA was told the
    unit was ON for minutes. Publishing nothing leaves the last known value and
    lets connected/state carry the fault.
    """
    p, serial, mqtt = _poller()
    serial.state = ConnectionState.ON
    serial.is_connected = True
    serial.send_command = AsyncMock(return_value=(False, None, "timeout"))
    await p.poll_once()
    published = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    assert "mv/power/state" not in published


@pytest.mark.asyncio
async def test_power_state_live_read_wins_over_stale_cached_state():
    # Cached `state` is stale-OFF (not yet refreshed by the 30s heartbeat),
    # but the transport is actually open and the device reports ON. The
    # live read must win over the stale cached ConnectionState.
    p, serial, mqtt = _poller()
    serial.state = ConnectionState.OFF
    serial.is_connected = True
    serial.send_command = AsyncMock(return_value=(True, "power on", None))
    await p.poll_once()
    published = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    assert published["mv/power/state"] == "ON"


@pytest.mark.asyncio
async def test_power_state_still_published_when_unavailable():
    # Port is down entirely: no branch should silently drop power/state.
    p, serial, mqtt = _poller()
    serial.state = ConnectionState.UNAVAILABLE
    serial.is_connected = False
    serial.send_command = AsyncMock(return_value=(False, None, "port unavailable"))
    await p.poll_once()
    published = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    assert published["mv/power/state"] == "OFF"


@pytest.mark.asyncio
async def test_nudged_poll_reads_the_config_class_group():
    """A command must confirm within one cycle, whatever group it lives in.

    Reported from the garage on 2026-08-29: toggling Source OSD turned the
    OSD off on the panel, but the HA toggle sprang back to ON for about a
    minute. trigger_immediate_poll only woke the loop early -- poll_once
    still gated the config-class read on `_cycle % SLOW_POLL_EVERY`, so the
    confirming state message waited for the next boundary. Source OSD,
    window border, the four border colours and the layout mode/aspect
    selects all sit in that group.
    """
    p, serial, mqtt = _poller()
    p._cycle = 1  # next cycle is 2 -- not a slow boundary
    serial.send_command = AsyncMock(return_value=(True, "source osd on", None))

    p.trigger_immediate_poll()
    await p.poll_once()

    topics = [c.args[0] for c in mqtt.publish.call_args_list]
    assert "mv/window/source_osd/state" in topics or "mv/output/hdcp/state" in topics, (
        "nudged cycle skipped the config-class group"
    )
    # The flag is one-shot: the following cycle goes back to the fast group.
    assert p._force_slow is False
    mqtt.publish.reset_mock()
    await p.poll_once()  # cycle 3
    topics = [c.args[0] for c in mqtt.publish.call_args_list]
    assert "mv/output/hdcp/state" not in topics


@pytest.mark.asyncio
async def test_nudge_during_an_in_flight_poll_is_not_erased():
    """A command landing mid-poll still gets its immediate next cycle.

    _run cleared _immediate_event *after* poll_once returned, so a nudge
    raised while the poll was in flight was wiped and the confirming read
    waited a full poll_interval. Drives the real _run loop: the second cycle
    must start promptly, not after poll_interval.
    """
    import asyncio

    p, serial, mqtt = _poller()
    p.settings.poll_interval = 30.0  # a lost nudge would wait this long
    starts: list[float] = []

    async def fake_poll_once():
        starts.append(asyncio.get_running_loop().time())
        if len(starts) == 1:
            await asyncio.sleep(0.05)
            p.trigger_immediate_poll()  # command arrives mid-poll
            await asyncio.sleep(0.05)
        else:
            p._stop_event.set()

    p.poll_once = fake_poll_once
    await asyncio.wait_for(p._run(), timeout=10)

    assert len(starts) >= 2, "second cycle never ran"
    assert starts[1] - starts[0] < 1.0, (
        f"nudge was erased: next cycle waited {starts[1] - starts[0]:.1f}s"
    )
