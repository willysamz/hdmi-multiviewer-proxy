import pytest
from unittest.mock import AsyncMock, MagicMock
from app.poller import Poller
from app.serial_handler import ConnectionState


def _poller():
    serial = MagicMock()
    serial.state = ConnectionState.ON
    mqtt = MagicMock()
    mqtt.publish = AsyncMock()
    settings = MagicMock()
    settings.mqtt_topic_prefix = "mv"
    settings.ha_discovery_enabled = False
    settings.poll_interval = 10.0
    p = Poller(serial, mqtt, settings)
    p._discovery_published = True  # skip discovery in these tests
    return p, serial, mqtt


@pytest.mark.asyncio
async def test_power_state_reads_device_not_connection():
    p, serial, mqtt = _poller()
    # Device answers "power off" even though the socket is up.
    serial.send_command = AsyncMock(return_value=(True, "power off", None))
    await p.poll_once()
    published = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    assert published["mv/power/state"] == "OFF"


@pytest.mark.asyncio
async def test_power_state_falls_back_to_connection_when_read_fails():
    p, serial, mqtt = _poller()
    serial.send_command = AsyncMock(return_value=(False, None, "timeout"))
    await p.poll_once()
    published = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    assert published["mv/power/state"] == "ON"  # socket up → assume on
