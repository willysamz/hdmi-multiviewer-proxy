"""Discovery must be device-scoped so multiple proxy instances coexist.

Regression guard: unique_id and the discovery topic must both include the
device_id, or a second instance (e.g. a garage unit) collides with the first
(basement) on shared retained topics + unique_ids and HA drops it.
"""

from app import discovery as d

_COMMON = dict(
    discovery_prefix="homeassistant",
    state_topic="s",
    command_topic="c",
    availability_topic="a",
)


def _power(device_id, device_name):
    return d.power_switch_payload(device_id=device_id, device_name=device_name, **_COMMON)


def test_unique_id_includes_device_id():
    _, payload = _power("garage_hdmi_multiviewer", "Garage HDMI Multiviewer")
    assert payload["unique_id"] == "garage_hdmi_multiviewer_multiviewer_power"
    # object_id stays the entity-name part (HA prefixes it with the device slug)
    assert payload["object_id"] == "multiviewer_power"


def test_topic_includes_device_id_as_node_id():
    topic, _ = _power("garage_hdmi_multiviewer", "Garage HDMI Multiviewer")
    assert topic == "homeassistant/switch/garage_hdmi_multiviewer/multiviewer_power/config"


def test_two_instances_do_not_collide():
    gt, gp = _power("garage_hdmi_multiviewer", "Garage HDMI Multiviewer")
    bt, bp = _power("hdmi_multiviewer", "HDMI Multiviewer")
    assert gt != bt
    assert gp["unique_id"] != bp["unique_id"]


def test_device_block_model_is_overridable():
    from app.discovery import device_block

    blk = device_block("garage_hdmi_multiviewer", "Garage HDMI Multiviewer", model="HDS-401MV")
    assert blk["model"] == "HDS-401MV"


def test_input_source_select_payload():
    from app.discovery import input_source_select_payload
    topic, payload = input_source_select_payload(
        discovery_prefix="homeassistant",
        device_id="garage_hdmi_multiviewer",
        device_name="Garage HDMI Multiviewer",
        state_topic="mv/input/source/state",
        command_topic="mv/input/source/set",
        availability_topic="mv/availability",
    )
    assert topic == "homeassistant/select/garage_hdmi_multiviewer/multiviewer_input_source/config"
    assert payload["object_id"] == "multiviewer_input_source"
    assert payload["options"] == ["HDMI 1", "HDMI 2", "HDMI 3", "HDMI 4"]
    assert payload["command_topic"] == "mv/input/source/set"
