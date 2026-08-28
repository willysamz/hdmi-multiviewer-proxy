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
