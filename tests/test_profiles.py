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


def test_edid_option_counts_come_from_firmware_not_the_manual():
    # The UHD manual lists 18 EDID modes; its firmware `help!` reports x=1~19.
    # Firmware wins -- an option the list omits is unreachable over MQTT.
    assert len(UHD_401MV.edid_options) == 19
    assert len(HDS_401MV.edid_options) == 7


def test_edid_command_case_follows_each_model():
    # The UHD manual prints `EDID`; the HDS `help!` prints `edid`. Since this
    # path has never been exercised on hardware, each uses its documented form.
    assert UHD_401MV.SET_INPUT_EDID == "s input EDID {x}!"
    assert HDS_401MV.SET_INPUT_EDID == "s input edid {x}!"


@pytest.mark.asyncio
async def test_edid_renders_the_1_based_index_for_the_chosen_label():
    c, serial = _controller("uhd401mv")
    await c.set_edid("1080P,Stereo Audio 2.0")  # 7th; note: no space after the comma
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


# --- Phase 5: full command exposure -----------------------------------------
# Response strings in these tests are VERBATIM captures from the live devices
# on 2026-08-28, not invented. The border-colour palette was enumerated by
# setting each index and reading the name back.


def test_border_colours_are_names_in_device_order():
    from app.profiles import BORDER_COLORS

    assert BORDER_COLORS == (
        "black", "red", "green", "blue", "yellow", "magenta", "cyan", "white", "gray",
    )
    # yellow is index 5 -- verified on hardware, and the value both garage
    # units were left on.
    assert BORDER_COLORS.index("yellow") + 1 == 5


@pytest.mark.asyncio
async def test_border_colour_renders_the_device_index():
    c, serial = _controller("hds401mv")
    await c.set_border_color(2, "yellow")
    serial.send_command.assert_awaited_once_with("s window 2 border color 5!")


@pytest.mark.asyncio
async def test_border_scope_differs_between_models():
    """Both models have borders; the COMMANDS are not the same.

    UHD: `s window x border y!` per window. HDS: `s window border y!` global.
    Modelling them as one command was the original error -- it came from the
    UHD manual, which omits the command entirely.
    """
    c_uhd, s_uhd = _controller("uhd401mv")
    await c_uhd.set_window_border_for(2, "ON")
    s_uhd.send_command.assert_awaited_once_with("s window 2 border 1!")
    with pytest.raises(ControllerError, match="per window"):
        await c_uhd.set_window_border("ON")

    c_hds, s_hds = _controller("hds401mv")
    await c_hds.set_window_border("OFF")
    s_hds.send_command.assert_awaited_once_with("s window border 0!")
    with pytest.raises(ControllerError, match="globally, not per window"):
        await c_hds.set_window_border_for(1, "ON")


def test_uhd_firmware_ranges_beat_its_manual_where_the_values_are_real():
    """Two of the manual's short lists were genuinely missing a value.

    Resolution and EDID gained a real 15th/19th entry (AUTO and USER1). The
    other three ranges `help!` reports are accept-ranges whose extra slots
    alias the last real value -- see
    test_ranges_help_reports_are_not_all_distinct_values.
    """
    assert len(UHD_401MV.resolution_options) == 15  # manual: 14
    assert len(UHD_401MV.edid_options) == 19  # manual: 18
    # The HDS keeps its smaller, help!-derived ranges.
    assert len(HDS_401MV.pip_position_options) == 4
    assert len(HDS_401MV.quad_mode_options) == 2


@pytest.mark.asyncio
async def test_hds_refuses_hdcp_vka_and_video_mode():
    c, serial = _controller("hds401mv")
    for call, msg in (
        (lambda: c.set_hdcp("HDCP 2.2"), "no HDCP command"),
        (lambda: c.set_vka("Black screen"), "no VKA command"),
        (lambda: c.set_video_mode("PC"), "no video-mode command"),
    ):
        with pytest.raises(ControllerError, match=msg):
            await call()
    serial.send_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_profile_without_resolution_labels_refuses_rather_than_guesses():
    """The guard still matters for any future model whose labels are unknown.

    The HDS had exactly this problem until its four were enumerated on
    hardware; a label-to-index mapping must never be invented.
    """
    from dataclasses import replace as _replace

    from app import profiles as P

    unlabelled = _replace(P.HDS_401MV, key="unlabelled", resolution_options=())
    P.PROFILES["unlabelled"] = unlabelled
    try:
        c, serial = _controller("unlabelled")
        with pytest.raises(ControllerError, match="no labelled resolution list"):
            await c.set_output_resolution("1920x1080p60")
        serial.send_command.assert_not_awaited()
    finally:
        P.PROFILES.pop("unlabelled", None)


@pytest.mark.asyncio
async def test_uhd_resolution_renders_the_manual_index():
    c, serial = _controller("uhd401mv")
    await c.set_output_resolution("1920x1080p60")  # 8th in the manual's table
    serial.send_command.assert_awaited_once_with("s output res 8!")


@pytest.mark.asyncio
async def test_hdcp_options_map_to_device_indices():
    c, serial = _controller("uhd401mv")
    await c.set_hdcp("HDCP 2.2")
    serial.send_command.assert_awaited_once_with("s output hdcp 2!")


@pytest.mark.asyncio
async def test_layout_setters_render_per_layout_and_kind():
    c, serial = _controller("uhd401mv")
    for call, expected in (
        (lambda: c.set_quad_aspect("16:9"), "s quad aspect 2!"),
        (lambda: c.set_pbp_aspect("Full screen"), "s PBP aspect 1!"),
        (lambda: c.set_triple_mode("Mode 2"), "s triple mode 2!"),
    ):
        serial.send_command.reset_mock()
        await call()
        serial.send_command.assert_awaited_once_with(expected)


@pytest.mark.asyncio
async def test_reboot_follows_the_model_prefix():
    c_uhd, s_uhd = _controller("uhd401mv")
    await c_uhd.reboot()
    s_uhd.send_command.assert_awaited_once_with("reboot!")

    c_hds, s_hds = _controller("hds401mv")
    await c_hds.reboot()
    s_hds.send_command.assert_awaited_once_with("s reboot!")


def test_new_parsers_against_verbatim_device_output():
    assert ResponseParser.parse_window_border("window border off") is False
    assert ResponseParser.parse_source_osd("window source osd:on") is True
    assert ResponseParser.parse_vka("output VKA pattern: black screen") == "black_screen"
    assert ResponseParser.parse_border_colors(
        "window 1 border color yellow\nwindow 2 border color red"
    ) == {1: "yellow", 2: "red"}


@pytest.mark.asyncio
async def test_discovery_entity_sets_differ_per_model():
    p_uhd, mqtt_uhd = _discovery_poller("uhd401mv")
    await p_uhd._publish_discovery()
    uhd = {c.args[0] for c in mqtt_uhd.publish.call_args_list if c.args[1] != ""}

    p_hds, mqtt_hds = _discovery_poller("hds401mv")
    await p_hds._publish_discovery()
    hds = {c.args[0] for c in mqtt_hds.publish.call_args_list if c.args[1] != ""}

    def has(topics, frag):
        return any(frag in t for t in topics)

    # UHD-only
    assert has(uhd, "multiviewer_hdcp") and not has(hds, "multiviewer_hdcp")
    # Both now have a resolution select: the HDS's four labels were enumerated
    # on hardware, so it no longer has to refuse.
    for topics in (uhd, hds):
        assert has(topics, "multiviewer_output_resolution")
    # Borders and OSD exist on BOTH -- absent from the UHD manual, present in
    # its firmware. Only the border SHAPE differs.
    for topics in (uhd, hds):
        assert has(topics, "window_1_border_color")
        assert has(topics, "multiviewer_source_osd")
    assert has(hds, "multiviewer_window_border")  # HDS: one global switch
    assert not has(uhd, "multiviewer_window_border")
    assert has(uhd, "multiviewer_window_1_border")  # UHD: one per window
    assert has(uhd, "multiviewer_window_4_border")
    # shared
    for topics in (uhd, hds):
        assert has(topics, "multiviewer_quad_aspect")
        assert has(topics, "multiviewer_pbp_aspect")
        assert has(topics, "multiviewer_reboot")


@pytest.mark.asyncio
async def test_reset_is_never_published():
    # reset discards the serial baud rate along with the layout. It must not
    # be reachable from a dashboard on either model.
    for key in ("uhd401mv", "hds401mv"):
        p, mqtt = _discovery_poller(key)
        await p._publish_discovery()
        assert not any("reset" in c.args[0] for c in mqtt.publish.call_args_list)


@pytest.mark.asyncio
async def test_hds_reports_its_real_edid_value_on_the_sensor():
    """`copy from hdmi out` is a VALID device value -- our HDS label set just
    does not contain it. It must be surfaced, not discarded."""
    p, mqtt = _discovery_poller("hds401mv")
    p._discovery_published = True
    from app.serial_handler import ConnectionState

    p.serial.is_connected = True
    p.serial.state = ConnectionState.ON
    p.serial.send_command = AsyncMock(return_value=(True, "input edid: copy from hdmi out", None))
    await p.poll_once()
    pub = {c.args[0]: c.args[1] for c in mqtt.publish.call_args_list}
    assert pub.get("mv/edid/mode/state") == "copy from hdmi out"


@pytest.mark.asyncio
async def test_edid_state_is_only_published_when_it_matches_an_option():
    # The HDS reports real mode names while its option list is still generic.
    # HA rejects a state absent from options[] and logs an error each time, so
    # an unguarded publish would error on every poll.
    p, mqtt = _discovery_poller("hds401mv")
    p._discovery_published = True
    p.serial.is_connected = True
    from app.serial_handler import ConnectionState

    p.serial.state = ConnectionState.ON
    p.serial.send_command = AsyncMock(return_value=(True, "input edid: copy from hdmi out", None))
    await p.poll_once()
    published = {c.args[0] for c in mqtt.publish.call_args_list}
    assert "mv/edid/state" not in published


# --- raw diagnostic endpoint ------------------------------------------------


def test_raw_endpoint_allowlist_accepts_only_reads():
    from app.routers.system import _is_read_only

    for ok in ("help!", "r output res!", "R INPUT EDID!", "  r power!  "):
        assert _is_read_only(ok), ok
    # Every setter must be refused -- including the two that can cost real
    # damage, and the prefixed forms the HDS uses.
    for bad in (
        "s output res 8!",
        "s input EDID 1!",
        "reset!",
        "s reset!",
        "reboot!",
        "s reboot!",
        "power 0!",
        "s power 0!",
        "r output res",       # no terminator
        "",
    ):
        assert not _is_read_only(bad), bad


# --- enumerated on hardware 2026-08-28 ---------------------------------------


def test_enumerated_edid_labels_match_device_output_exactly():
    """A label that differs even by whitespace never matches the reported state.

    The device emits `4K2K60_444,Stereo Audio 2.0` with no space after the
    comma; prettifying it broke the match silently.
    """
    assert UHD_401MV.edid_options[0] == "4K2K60_444,Stereo Audio 2.0"
    # `s input EDID 19!` reads back USER1 -- confirmed on hardware.
    assert UHD_401MV.edid_options[-1] == "USER1"
    assert len(UHD_401MV.edid_options) == 19


def test_ranges_help_reports_are_not_all_distinct_values():
    """`help!` gives what the parser ACCEPTS, not how many values exist.

    Enumerated: quad mode 3 -> "quad mode 2", PIP position 5 -> "right bottom"
    (= 4), PIP size 4 -> "large" (= 3). Offering those slots would be a control
    that silently does nothing, so they are not offered.
    """
    assert len(UHD_401MV.quad_mode_options) == 2  # help! says x=1~3
    assert len(UHD_401MV.pip_position_options) == 4  # help! says x=1~5
    assert len(UHD_401MV.pip_size_options) == 3  # help! says x=1~4


def test_resolution_keeps_auto_as_the_fifteenth():
    # Inferred, not proven -- see the profile comment.
    assert UHD_401MV.resolution_options[-1] == "AUTO"
    assert len(UHD_401MV.resolution_options) == 15


def test_border_colour_parser_handles_both_device_formats():
    from app.commands import ResponseParser as R

    # HDS: bare word. UHD: colon, and empty when unset.
    assert R.parse_border_colors("window 1 border color yellow") == {1: "yellow"}
    assert R.parse_border_colors("window 1 border color: blue") == {1: "blue"}
    # Empty values are omitted, not returned blank -- and the newline must not
    # let the next line's first word be captured as this line's colour.
    assert R.parse_border_colors(
        "window 1 border color:\nwindow 2 border color:\n"
        "window 3 border color:\nwindow 4 border color:"
    ) == {}


def test_hds_resolution_labels_were_enumerated_from_hardware():
    """The HDS names its 4 resolutions nowhere; each index was set and read
    back. Labels must match the device's exact reply or the state never
    matches an option."""
    assert HDS_401MV.resolution_options == (
        "3840x2160p30",
        "1920x1080p60",
        "1280x720p60",
        "1920x1200p60(rb)",
    )


@pytest.mark.asyncio
async def test_hds_resolution_now_renders_an_index():
    c, serial = _controller("hds401mv")
    await c.set_output_resolution("1280x720p60")  # 3rd
    serial.send_command.assert_awaited_once_with("s output res 3!")
