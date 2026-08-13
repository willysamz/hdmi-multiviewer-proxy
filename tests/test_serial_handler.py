"""Tests for SerialHandler transport selection (device path vs socket:// URL)."""

import asyncio

import serial

from app.serial_handler import ConnectionState, SerialHandler


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _noop():
    return None


class _FakeSerial:
    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass


def test_is_url_detection():
    assert SerialHandler("socket://192.168.1.80:6638")._is_url is True
    assert SerialHandler("rfc2217://host:5000")._is_url is True
    assert SerialHandler("/dev/ttyUSB0")._is_url is False


def test_socket_url_uses_serial_for_url(monkeypatch):
    calls = {}

    def fake_for_url(url, **kw):
        calls["url"] = url
        return _FakeSerial()

    def fake_serial(**kw):
        calls["serial"] = True
        return _FakeSerial()

    monkeypatch.setattr(serial, "serial_for_url", fake_for_url)
    monkeypatch.setattr(serial, "Serial", fake_serial)

    h = SerialHandler("socket://192.168.1.80:6638", timeout=1.0)
    monkeypatch.setattr(h, "_check_power_state", _noop)

    ok = _run(h._try_connect())

    assert ok is True
    assert calls.get("url") == "socket://192.168.1.80:6638"
    # A URL port must NOT go through serial.Serial nor the existence gate.
    assert "serial" not in calls


def test_device_path_missing_is_unavailable(monkeypatch):
    # A non-existent device path is rejected before any open attempt.
    monkeypatch.setattr("os.path.exists", lambda p: False)
    h = SerialHandler("/dev/ttyUSB0")
    ok = _run(h._try_connect())
    assert ok is False
    assert h.state == ConnectionState.UNAVAILABLE


class _OpenSerial(_FakeSerial):
    is_open = True

    def write(self, *a):
        return None

    def flush(self):
        return None


def test_empty_response_does_not_reconnect(monkeypatch):
    import serial
    from app.serial_handler import ConnectionState
    h = SerialHandler("socket://192.168.1.80:6638", timeout=0.1)
    h._serial = _OpenSerial()
    h._state = ConnectionState.ON

    async def _none(_cmd):
        return None
    monkeypatch.setattr(h, "_send_command_internal", _none)
    flags = {"disc": False, "sched": False}
    async def _disc():
        flags["disc"] = True
    monkeypatch.setattr(h, "_disconnect", _disc)
    monkeypatch.setattr(h, "_schedule_reconnect", lambda: flags.__setitem__("sched", True))

    ok, resp, err = _run(h.send_command("r pip size!"))
    assert ok is False and err == "no_response"
    assert flags["disc"] is False and flags["sched"] is False


def test_transport_error_reconnects(monkeypatch):
    import serial
    from app.serial_handler import ConnectionState
    h = SerialHandler("socket://192.168.1.80:6638", timeout=0.1)
    h._serial = _OpenSerial()
    h._state = ConnectionState.ON

    async def _raise(_cmd):
        raise serial.SerialException("boom")
    monkeypatch.setattr(h, "_send_command_internal", _raise)
    flags = {"disc": False, "sched": False}
    async def _disc():
        flags["disc"] = True
    monkeypatch.setattr(h, "_disconnect", _disc)
    monkeypatch.setattr(h, "_schedule_reconnect", lambda: flags.__setitem__("sched", True))

    ok, resp, err = _run(h.send_command("r pip size!"))
    assert ok is False and err == "device_communication_error"
    assert flags["disc"] is True and flags["sched"] is True
