"""Home Assistant MQTT discovery payload + topic builders.

Every entity pins `object_id` to the entity_id it should land at in HA,
so existing dashboards / scripts / automations referencing those
entity_ids keep working after Phase 2 (which removes the legacy
`input_select` / `input_number` / `binary_sensor` / `template switch`
configuration from configuration.yaml).
"""

from __future__ import annotations

from typing import Any

DEVICE_MANUFACTURER = "MT-VIKI"
DEVICE_MODEL = "UHD-401MV 4-port HDMI Multiviewer"

# These string lists drive the `select` entities' `options[]` arrays.
# Must match what `controller.py` accepts on the `*/set` topics + what
# `poller.py` publishes on the `*/state` topics.
MULTIVIEW_MODES = ["single", "pip", "pbp", "triple", "quad"]
WINDOW_INPUTS = ["HDMI 1", "HDMI 2", "HDMI 3", "HDMI 4"]
AUDIO_SOURCES = ["Follow Window 1", "HDMI 1", "HDMI 2", "HDMI 3", "HDMI 4"]
PIP_POSITIONS = ["Top Left", "Bottom Left", "Top Right", "Bottom Right"]
PIP_SIZES = ["Small", "Medium", "Large"]


def device_block(device_id: str, device_name: str, model: str = DEVICE_MODEL) -> dict[str, Any]:
    """The `device` field repeated on every entity payload — pins them
    all to one HA device card."""
    return {
        "identifiers": [device_id],
        "name": device_name,
        "manufacturer": DEVICE_MANUFACTURER,
        "model": model,
    }


def _base_payload(
    *,
    object_id: str,
    name: str,
    state_topic: str,
    availability_topic: str,
    device_id: str,
    device_name: str,
    model: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "unique_id": f"{device_id}_{object_id}",
        "object_id": object_id,
        "state_topic": state_topic,
        "availability_topic": availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device_block(device_id, device_name, model or DEVICE_MODEL),
    }
    if extra:
        payload.update(extra)
    return payload


def power_switch_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    command_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`switch.multiviewer_power` — replaces the legacy template switch."""
    object_id = "multiviewer_power"
    topic = f"{discovery_prefix}/switch/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer Power",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "command_topic": command_topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:monitor",
            "optimistic": False,
        },
    )
    return topic, payload


def connected_binary_sensor_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`binary_sensor.multiviewer_connected` — serial reachability."""
    object_id = "multiviewer_connected"
    topic = f"{discovery_prefix}/binary_sensor/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer Connected",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "device_class": "connectivity",
            "payload_on": "ON",
            "payload_off": "OFF",
        },
    )
    return topic, payload


def _select_payload(
    *,
    object_id: str,
    name: str,
    icon: str,
    options: list[str],
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    command_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    topic = f"{discovery_prefix}/select/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name=name,
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "command_topic": command_topic,
            "options": options,
            "icon": icon,
            "optimistic": False,
        },
    )
    return topic, payload


def mode_select_payload(**kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_mode` — single/pip/pbp/triple/quad."""
    return _select_payload(
        object_id="multiviewer_mode",
        name="Multiviewer Mode",
        icon="mdi:monitor",
        options=MULTIVIEW_MODES,
        **kw,
    )


def window_select_payload(window_n: int, **kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_window_N_input` — HDMI 1..4."""
    return _select_payload(
        object_id=f"multiviewer_window_{window_n}_input",
        name=f"Window {window_n} Input",
        icon="mdi:monitor-screenshot",
        options=WINDOW_INPUTS,
        **kw,
    )


def input_source_select_payload(**kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_input_source` — single-screen source, HDMI 1..4.
    Distinct from the window inputs: single mode is driven by `s in source`."""
    return _select_payload(
        object_id="multiviewer_input_source",
        name="Single-Screen Input",
        icon="mdi:import",
        options=WINDOW_INPUTS,
        **kw,
    )


def audio_source_select_payload(**kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_audio_source` — Follow Window 1 / HDMI 1..4."""
    return _select_payload(
        object_id="multiviewer_audio_source",
        name="Multiviewer Audio",
        icon="mdi:speaker",
        options=AUDIO_SOURCES,
        **kw,
    )


def pip_position_select_payload(**kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_pip_position` — TL/TR/BL/BR."""
    return _select_payload(
        object_id="multiviewer_pip_position",
        name="PIP Position",
        icon="mdi:picture-in-picture-top-right",
        options=PIP_POSITIONS,
        **kw,
    )


def pip_size_select_payload(**kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_pip_size` — Small/Medium/Large."""
    return _select_payload(
        object_id="multiviewer_pip_size",
        name="PIP Size",
        icon="mdi:resize",
        options=PIP_SIZES,
        **kw,
    )


def volume_number_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    command_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`number.multiviewer_volume` — 0..100 step 5."""
    object_id = "multiviewer_volume"
    topic = f"{discovery_prefix}/number/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer Volume",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "command_topic": command_topic,
            "min": 0,
            "max": 100,
            "step": 5,
            "unit_of_measurement": "%",
            "icon": "mdi:volume-high",
            "mode": "slider",
            "optimistic": False,
        },
    )
    return topic, payload


def mute_switch_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    command_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`switch.multiviewer_muted` — writable. Today this is a read-only
    binary_sensor; promoting to a switch unlocks toggle UX in HA."""
    object_id = "multiviewer_muted"
    topic = f"{discovery_prefix}/switch/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer Mute",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "command_topic": command_topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:volume-mute",
            "optimistic": False,
        },
    )
    return topic, payload


def resolution_sensor_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`sensor.multiviewer_resolution` — read-only output resolution."""
    object_id = "multiviewer_resolution"
    topic = f"{discovery_prefix}/sensor/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer Resolution",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "icon": "mdi:monitor-shimmer",
        },
    )
    return topic, payload
