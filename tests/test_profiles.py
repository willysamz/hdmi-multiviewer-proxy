"""Device-profile tests.

These are the regression guard for the 0.3.4 incident: power was changed to
the `s `-prefixed form, which is right for the HDS-401MV and silently ignored
by the UHD-401MV. Both forms are asserted here so neither can be "fixed" into
the other again.

EDID and reset are exercised ONLY as rendered command strings. Nothing here
sends them anywhere -- setting a real EDID renegotiates HDMI for all four
sources and can black the display or drop audio, and reset discards the serial
baud rate along with the layout.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.commands import ResponseParser
from app.controller import Controller, ControllerError
from app.profiles import (
    CAP_AUTO_SWITCH,
    CAP_EDID,
    CAP_HDCP,
    CAP_ITC,
    CAP_VKA,
    CAP_VOLUME,
    HDS_401MV,
    UHD_401MV,
    get_profile,
)


def _controller(profile_key: str):
    serial = MagicMock()
    serial.send_command = AsyncMock(return_value=(True, "ok", None))
    settings = MagicMock()
    settings.device_profile = profile_key
    return Controller(serial, MagicMock(), MagicMock(), settings), serial


# --- profile lookup ---------------------------------------------------------


def test_get_profile_is_case_and_space_insensitive():
    assert get_profile("  UHD401MV ") is UHD_401MV


def test_unknown_profile_raises_rather_than_defaulting():
    # Silently falling back to a default is how a typo would reintroduce the
    # exact bug this module exists to prevent.
    with pytest.raises(ValueError, match="unknown device_profile"):
        get_profile("uhd-401mv")


# --- the regression itself --------------------------------------------------


def test_uhd_power_is_unprefixed():
    # Confirmed on hardware: `power 1!` woke the unit; `s power 0!` did nothing
    # for 14 hours. The UHD's SYSTEM block is the only unprefixed group.
    assert UHD_401MV.POWER_ON == "power 1!"
    assert UHD_401MV.POWER_OFF == "power 0!"


def test_hds_power_is_prefixed():
    # Confirmed on hardware: `s power 1!` woke the garage unit.
    assert HDS_401MV.POWER_ON == "s power 1!"
    assert HDS_401MV.POWER_OFF == "s power 0!"


def test_power_forms_differ_between_models():
    assert UHD_401MV.POWER_ON != HDS_401MV.POWER_ON


def test_reboot_and_reset_follow_the_same_split():
    # The latent half of the same bug: before profiles, the code shipped
    # prefixed power with UNprefixed reboot/reset, so one model was wrong
    # either way. Nothing had called them yet.
    assert (UHD_401MV.REBOOT, UHD_401MV.RESET) == ("reboot!", "reset!")
    assert (HDS_401MV.REBOOT, HDS_401MV.RESET) == ("s reboot!", "s reset!")


@pytest.mark.asyncio
async def test_controller_sends_the_right_power_command_per_profile():
    c_uhd, serial_uhd = _controller("uhd401mv")
    await c_uhd.set_power("ON")
    serial_uhd.send_command.assert_awaited_once_with("power 1!")

    c_hds, serial_hds = _controller("hds401mv")
    await c_hds.set_power("ON")
    serial_hds.send_command.assert_awaited_once_with("s power 1!")


# --- capabilities -----------------------------------------------------------


def test_hds_has_no_volume_hdcp_vka_or_itc():
    # Its `help!` lists 46 commands and none of these are among them. Polling
    # them returns `E00`; publishing entities for them creates dead controls.
    for cap in (CAP_VOLUME, CAP_HDCP, CAP_VKA, CAP_ITC):
        assert not HDS_401MV.supports(cap)


def test_uhd_has_volume():
    assert UHD_401MV.supports(CAP_VOLUME)


def test_both_models_support_edid_and_auto_switch():
    for profile in (UHD_401MV, HDS_401MV):
        assert profile.supports(CAP_EDID)
        assert profile.supports(CAP_AUTO_SWITCH)


@pytest.mark.asyncio
async def test_volume_is_refused_on_hds_rather_than_sent():
    c, serial = _controller("hds401mv")
    with pytest.raises(ControllerError, match="no volume command"):
        await c.set_audio_volume("40")
    serial.send_command.assert_not_awaited()


# --- auto switch ------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_switch_on_and_off():
    c, serial = _controller("uhd401mv")
    await c.set_auto_switch("OFF")
    serial.send_command.assert_awaited_once_with("s auto switch 0!")
    serial.send_command.reset_mock()
    await c.set_auto_switch("ON")
    serial.send_command.assert_awaited_once_with("s auto switch 1!")


@pytest.mark.asyncio
async def test_auto_switch_rejects_junk():
    c, serial = _controller("uhd401mv")
    with pytest.raises(ControllerError, match="invalid auto switch"):
        await c.set_auto_switch("MAYBE")
    serial.send_command.assert_not_awaited()


def test_auto_switch_response_parsing():
    assert ResponseParser.parse_auto_switch("auto switch off") is False
    assert ResponseParser.parse_auto_switch("auto switch on") is True
    assert ResponseParser.parse_auto_switch("something else") is None


# --- EDID (string rendering only -- never sent to a device) -----------------


def test_edid_option_counts_differ_per_model():
    # UHD manual lists 18 modes; the HDS `help!` gives x=1~7 with no labels.
    assert len(UHD_401MV.edid_options) == 18
    assert len(HDS_401MV.edid_options) == 7


def test_edid_command_case_follows_each_model():
    # The UHD manual prints `EDID`; the HDS `help!` prints `edid`. Since this
    # path has never been exercised on hardware, each uses its documented form.
    assert UHD_401MV.SET_INPUT_EDID == "s input EDID {x}!"
    assert HDS_401MV.SET_INPUT_EDID == "s input edid {x}!"


@pytest.mark.asyncio
async def test_edid_renders_the_1_based_index_for_the_chosen_label():
    c, serial = _controller("uhd401mv")
    await c.set_edid("1080P, Stereo Audio 2.0")  # 7th in the manual's list
    serial.send_command.assert_awaited_once_with("s input EDID 7!")


@pytest.mark.asyncio
async def test_edid_label_match_is_case_insensitive():
    c, serial = _controller("uhd401mv")
    await c.set_edid("copy from hdmi out")  # 18th
    serial.send_command.assert_awaited_once_with("s input EDID 18!")


@pytest.mark.asyncio
async def test_edid_rejects_a_label_the_model_does_not_have():
    # An HDS has 7 modes, so a UHD label must not be passed through as an index.
    c, serial = _controller("hds401mv")
    with pytest.raises(ControllerError, match="invalid EDID mode"):
        await c.set_edid("Copy from HDMI out")
    serial.send_command.assert_not_awaited()


def test_edid_response_parsing_handles_both_cases():
    assert (
        ResponseParser.parse_edid("input EDID:4K2K60_444,Stereo Audio 2.0")
        == "4K2K60_444,Stereo Audio 2.0"
    )
    assert ResponseParser.parse_edid("input edid: 1080P") == "1080P"
    assert ResponseParser.parse_edid("no match here") is None


# --- discovery gating -------------------------------------------------------


def _discovery_poller(profile_key: str):
    from app.poller import Poller

    serial = MagicMock()
    mqtt = MagicMock()
    mqtt.publish = AsyncMock()
    mqtt.availability_topic = "mv/availability"
    settings = MagicMock()
    settings.mqtt_topic_prefix = "mv"
    settings.ha_discovery_enabled = True
    settings.ha_discovery_prefix = "homeassistant"
    settings.ha_device_id = "mvtest"
    settings.ha_device_name = "MV Test"
    settings.ha_device_model = "test"
    settings.poll_interval = 10.0
    settings.device_profile = profile_key
    return Poller(serial, mqtt, settings), mqtt


VOLUME_CONFIG_TOPIC = "homeassistant/number/mvtest/multiviewer_volume/config"


@pytest.mark.asyncio
async def test_hds_retracts_the_volume_entity():
    # A phantom volume entity really existed on the garage unit, left over from
    # an era when both models shared one entity set. An empty retained payload
    # is how HA deletes a previously-discovered entity, so publishing one is
    # what actually clears it -- simply not publishing would leave it forever.
    p, mqtt = _discovery_poller("hds401mv")
    await p._publish_discovery()
    published = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    assert published[VOLUME_CONFIG_TOPIC] == ""


@pytest.mark.asyncio
async def test_uhd_publishes_the_volume_entity():
    p, mqtt = _discovery_poller("uhd401mv")
    await p._publish_discovery()
    published = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    assert published[VOLUME_CONFIG_TOPIC] != ""


@pytest.mark.asyncio
async def test_edid_select_options_come_from_the_profile():
    p, mqtt = _discovery_poller("hds401mv")
    await p._publish_discovery()
    published = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    edid = published["homeassistant/select/mvtest/multiviewer_edid/config"]
    assert len(edid["options"]) == 7
    # EDID is disruptive; it belongs in HA's config block, not the main card.
    assert edid["entity_category"] == "config"
