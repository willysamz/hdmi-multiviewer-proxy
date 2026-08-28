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
    entity_category: str | None = None,
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
            **({"entity_category": entity_category} if entity_category else {}),
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


def auto_switch_switch_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    command_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`switch.multiviewer_auto_switch` — automatic input failover.

    When on, the device jumps to the next live input if the current source
    drops. That competes with scenes/scripts that set an input explicitly, so
    being able to see and disable it matters more than being able to enable it.
    """
    object_id = "multiviewer_auto_switch"
    topic = f"{discovery_prefix}/switch/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer Auto Switch",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "command_topic": command_topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:swap-horizontal-bold",
            "optimistic": False,
            "entity_category": "config",
        },
    )
    return topic, payload


def edid_select_payload(
    *,
    options: list[str],
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    command_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_edid` — the EDID presented to all four inputs.

    Options are profile-supplied: the models expose different mode counts
    (UHD 18, HDS 7) and their labels are not interchangeable.

    Marked `entity_category: config` so it lands in HA's configuration block
    rather than on the main card. Changing it renegotiates HDMI for every
    source and can black the display or drop audio, so it should not sit
    somewhere it can be brushed by accident.
    """
    object_id = "multiviewer_edid"
    topic = f"{discovery_prefix}/select/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer EDID",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "command_topic": command_topic,
            "options": options,
            "icon": "mdi:high-definition-box",
            "optimistic": False,
            "entity_category": "config",
        },
    )
    return topic, payload


# --- Phase 5: full command exposure -----------------------------------------
# Selects whose options come from the active profile, plus the HDS-only border
# and OSD controls. Set-and-forget entities carry entity_category="config" so
# HA files them under the device's configuration block rather than the main
# card.


def resolution_select_payload(*, options: list[str], **kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_output_resolution` — settable output resolution.

    Published only for a profile that has labelled options. It coexists with
    the resolution *sensor*: the sensor reports the device's truth (which can
    be `AUTO`, a value absent from the settable list), while this select offers
    only what can actually be set.
    """
    return _select_payload(
        object_id="multiviewer_output_resolution",
        name="Multiviewer Output Resolution",
        icon="mdi:monitor-screenshot",
        options=options,
        **kw,
    )


def hdcp_select_payload(*, options: list[str], **kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_hdcp` — what the output advertises downstream.

    Not filed under config: this is the first thing to reach for when a
    protected source (a games console) shows black through the multiviewer.
    """
    return _select_payload(
        object_id="multiviewer_hdcp",
        name="Multiviewer HDCP",
        icon="mdi:shield-lock-outline",
        options=options,
        **kw,
    )


def vka_select_payload(*, options: list[str], **kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_vka` — pattern shown when no source is present.

    Keeps the HDMI link up so the display does not drop the signal and
    re-handshake, which is the multi-second black flash when a source sleeps.
    """
    return _select_payload(
        object_id="multiviewer_vka",
        name="Multiviewer VKA Pattern",
        icon="mdi:television-shimmer",
        options=options,
        entity_category="config",
        **kw,
    )


def video_mode_select_payload(*, options: list[str], **kw: Any) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_video_mode` — IT Content flag (video vs PC).

    PC mode asks the display for 1:1 pixel mapping and usually lower latency.
    """
    return _select_payload(
        object_id="multiviewer_video_mode",
        name="Multiviewer Video Mode",
        icon="mdi:monitor-eye",
        options=options,
        entity_category="config",
        **kw,
    )


def layout_select_payload(
    *, layout: str, kind: str, options: list[str], **kw: Any
) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_{layout}_{kind}` for quad / pbp / triple.

    `aspect` matters far more outside quad: quad cells are already 16:9 so a
    16:9 source fills them either way, while PBP cells are roughly 8:9 and
    triple narrower still, so `Full screen` visibly squashes every source.
    Quad is left on the main card for the one source that is not 16:9.
    """
    return _select_payload(
        object_id=f"multiviewer_{layout}_{kind}",
        name=f"Multiviewer {layout.upper() if layout != 'triple' else 'Triple'} {kind.capitalize()}",
        icon="mdi:view-grid-outline" if kind == "mode" else "mdi:aspect-ratio",
        options=options,
        **({} if layout == "quad" else {"entity_category": "config"}),
        **kw,
    )


def border_color_select_payload(
    window_n: int, *, options: list[str], **kw: Any
) -> tuple[str, dict[str, Any]]:
    """`select.multiviewer_window_{n}_border_color` — HDS only.

    Options are colour NAMES because the device reports names, never indices;
    an index-labelled list would publish a state matching no option.
    """
    return _select_payload(
        object_id=f"multiviewer_window_{window_n}_border_color",
        name=f"Multiviewer Window {window_n} Border Colour",
        icon="mdi:border-color",
        options=options,
        **kw,
    )


def window_border_switch_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    command_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`switch.multiviewer_window_border` — HDS only. Draws a border round
    every window, which is what separates adjacent tiles in quad."""
    object_id = "multiviewer_window_border"
    topic = f"{discovery_prefix}/switch/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer Window Border",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "command_topic": command_topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:border-all-variant",
            "optimistic": False,
        },
    )
    return topic, payload


def source_osd_switch_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    command_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`switch.multiviewer_source_osd` — HDS only. Labels each window with the
    input it is showing, so a tile can be identified without counting corners."""
    object_id = "multiviewer_source_osd"
    topic = f"{discovery_prefix}/switch/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer Source OSD",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={
            "command_topic": command_topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:format-text",
            "optimistic": False,
        },
    )
    return topic, payload


def reboot_button_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    command_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`button.multiviewer_reboot` — restart the unit.

    Config category deliberately: it drops video for the init cycle, so it
    should not sit where it can be brushed. `reset` is never published at all.
    """
    object_id = "multiviewer_reboot"
    topic = f"{discovery_prefix}/button/{device_id}/{object_id}/config"
    payload: dict[str, Any] = {
        "name": "Multiviewer Reboot",
        "unique_id": f"{device_id}_{object_id}",
        "object_id": object_id,
        "command_topic": command_topic,
        "payload_press": "PRESS",
        "availability_topic": availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
        "icon": "mdi:restart",
        "entity_category": "config",
        "device": device_block(device_id, device_name, model or DEVICE_MODEL),
    }
    return topic, payload


def edid_sensor_payload(
    *,
    discovery_prefix: str,
    device_id: str,
    device_name: str,
    state_topic: str,
    availability_topic: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """`sensor.multiviewer_edid_mode` — the EDID mode the device reports.

    Published only when the profile's select options are placeholders rather
    than the device's real mode names. The device's value is valid; our list
    just does not contain it, and hiding a true reading behind an incomplete
    label set would be the wrong trade.
    """
    object_id = "multiviewer_edid_mode"
    topic = f"{discovery_prefix}/sensor/{device_id}/{object_id}/config"
    payload = _base_payload(
        object_id=object_id,
        name="Multiviewer EDID Mode",
        state_topic=state_topic,
        availability_topic=availability_topic,
        device_id=device_id,
        device_name=device_name,
        model=model,
        extra={"icon": "mdi:high-definition-box", "entity_category": "diagnostic"},
    )
    return topic, payload
