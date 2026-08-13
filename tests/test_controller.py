from unittest.mock import AsyncMock, MagicMock

import pytest

from app.controller import Controller


@pytest.mark.asyncio
async def test_set_input_source_sends_s_in_source():
    serial = MagicMock()
    serial.send_command = AsyncMock(return_value=(True, "input source: hdmi 3", None))
    poller = MagicMock()
    c = Controller(serial, MagicMock(), poller, MagicMock())
    await c.set_input_source("HDMI 3")
    serial.send_command.assert_awaited_once_with("s in source 3!")
