"""Per-device command profiles.

The proxy drives more than one OREI 4x1 multiviewer, and they are **not**
command-compatible. Treating them as one device caused a production regression:
0.3.4 changed power to the `s `-prefixed form, which is correct for the
HDS-401MV and silently ignored by the UHD-401MV.

A profile carries three things:

* **command templates** — the exact wire string per logical operation
* **capabilities** — which operations the device has *at all*
* **parameter domains** — valid values and their labels

Sources (both primary, no guessing):

* UHD-401MV — vendor manual, RS-232 Command section.
* HDS-401MV — `help!` sent to the live device, which returns all 46 commands.

`r type!` returns ``4x1 HDMI Multiviewer`` on **both**, so the model cannot be
auto-detected from the device. The profile is explicit configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

# --- Capability tokens -------------------------------------------------------
# A capability gates BOTH polling and HA discovery. If a device lacks one, the
# proxy must never query it (the device answers with an error) and must never
# publish an entity for it (HA would show a control that cannot work).

CAP_VOLUME = "volume"  # s output audio vol / vol+ / vol-
CAP_HDCP = "hdcp"  # s output hdcp
CAP_VKA = "vka"  # s output vka
CAP_ITC = "itc"  # s output itc (video/pc mode)
CAP_EDID = "edid"  # s input edid
CAP_AUTO_SWITCH = "auto_switch"  # s auto switch
CAP_STATUS = "status"  # r status! (HDS only)
CAP_WINDOW_BORDER = "window_border"  # HDS only, not yet exposed
CAP_SOURCE_OSD = "source_osd"  # HDS only, not yet exposed


# --- EDID option domains -----------------------------------------------------
# UHD labels are transcribed from its manual. The HDS `help!` gives only the
# range (x=1~7) with no labels and we have no HDS manual, so its options stay
# generic rather than inventing names that might mislead.

UHD_EDID_OPTIONS: tuple[str, ...] = (
    "4K2K60_444, Stereo Audio 2.0",
    "4K2K60_444, Dolby/DTS 5.1",
    "4K2K60_444, HD Audio 7.1",
    "4K2K30_444, Stereo Audio 2.0",
    "4K2K30_444, Dolby/DTS 5.1",
    "4K2K30_444, HD Audio 7.1",
    "1080P, Stereo Audio 2.0",
    "1080P, Dolby/DTS 5.1",
    "1080P, HD Audio 7.1",
    "1920x1200, Stereo Audio 2.0",
    "1680x1050, Stereo Audio 2.0",
    "1600x1200, Stereo Audio 2.0",
    "1440x900, Stereo Audio 2.0",
    "1360x768, Stereo Audio 2.0",
    "1280x1024, Stereo Audio 2.0",
    "1024x768, Stereo Audio 2.0",
    "720p, Stereo Audio 2.0",
    "Copy from HDMI out",
    # 19th slot: firmware accepts x=1~19 while the manual lists 18. `s edid
    # user1 ...!` exists, so this is plausibly the user-defined EDID -- but
    # that is inference, so it stays a placeholder until read back.
    "Option 19",
)

HDS_EDID_OPTIONS: tuple[str, ...] = tuple(f"EDID mode {n}" for n in range(1, 8))

# Border colours, enumerated from the live HDS on 2026-08-28 by setting each
# index and reading the name back. The device reports NAMES (`yellow`), never
# indices, so these must be the select's options or the published state would
# never match one.
BORDER_COLORS: tuple[str, ...] = (
    "black",
    "red",
    "green",
    "blue",
    "yellow",
    "magenta",
    "cyan",
    "white",
    "gray",
)

# Output-resolution labels. The UHD's 14 come from its manual. The HDS accepts
# x=1~4 but names them nowhere, and it reports real resolution strings
# (`1920x1080p60`), so an index-labelled select would publish a state matching
# no option. Left empty until the names are captured; the read-only resolution
# sensor covers that model meanwhile.
UHD_RESOLUTION_OPTIONS: tuple[str, ...] = (
    "4096x2160p60",
    "4096x2160p50",
    "3840x2160p60",
    "3840x2160p50",
    "3840x2160p30",
    "3840x2160p25",
    "1920x1200p60RB",
    "1920x1080p60",
    "1920x1080p50",
    "1360x768p60",
    "1280x800p60",
    "1280x720p60",
    "1280x720p50",
    "1024x768p60",
    # 15th slot: firmware accepts x=1~15, the manual lists 14, and the device
    # reports AUTO -- absent from that table. Almost certainly this. Selecting
    # it while already on AUTO is a no-op, so it self-confirms.
    "Option 15",
)
HDS_RESOLUTION_OPTIONS: tuple[str, ...] = ()

ASPECT_OPTIONS: tuple[str, ...] = ("Full screen", "16:9")
LAYOUT_MODE_OPTIONS: tuple[str, ...] = ("Mode 1", "Mode 2")

# The UHD firmware (MCU 1.10.03) accepts wider ranges than its manual
# documents, discovered by running `help!` against the unit. Where the extra
# slot has no known name it carries a placeholder: the option must EXIST for
# the value to be reachable over MQTT at all, and a placeholder that can be
# selected beats a value that cannot.
QUAD_MODE_OPTIONS_UHD: tuple[str, ...] = ("Mode 1", "Mode 2", "Mode 3")
PIP_POSITION_OPTIONS: tuple[str, ...] = (
    "Top Left",
    "Bottom Left",
    "Top Right",
    "Bottom Right",
)
PIP_POSITION_OPTIONS_UHD: tuple[str, ...] = PIP_POSITION_OPTIONS + ("Position 5",)
PIP_SIZE_OPTIONS: tuple[str, ...] = ("Small", "Medium", "Large")
PIP_SIZE_OPTIONS_UHD: tuple[str, ...] = PIP_SIZE_OPTIONS + ("Size 4",)
HDCP_OPTIONS: tuple[str, ...] = ("HDCP 1.4", "HDCP 2.2", "Off")
VKA_OPTIONS: tuple[str, ...] = ("Black screen", "Blue screen")
VIDEO_MODE_OPTIONS: tuple[str, ...] = ("Video", "PC")


@dataclass(frozen=True)
class DeviceProfile:
    """One device model's command set, capabilities and parameter domains.

    Command attributes deliberately mirror the historic ``Commands`` class
    names so call sites read the same; only the lookup moves from a module
    constant to the active profile.
    """

    key: str
    model: str

    # --- System. The prefix differs per model and IS the regression. ---
    POWER_ON: str
    POWER_OFF: str
    REBOOT: str
    RESET: str
    GET_POWER: str = "r power!"
    HELP: str = "help!"
    GET_TYPE: str = "r type!"
    GET_FW_VERSION: str = "r fw version!"

    # --- EDID. Case differs: the UHD manual prints `EDID`, the HDS `edid`. ---
    SET_INPUT_EDID: str = "s input EDID {x}!"
    GET_INPUT_EDID: str = "r input EDID!"

    # --- Shared. Verified identical on both models. ---
    SET_OUTPUT_RES: str = "s output res {x}!"
    GET_OUTPUT_RES: str = "r output res!"
    SET_OUTPUT_HDCP: str = "s output hdcp {x}!"
    GET_OUTPUT_HDCP: str = "r output hdcp!"
    SET_OUTPUT_VKA: str = "s output vka {x}!"
    GET_OUTPUT_VKA: str = "r output vka!"
    SET_OUTPUT_ITC: str = "s output itc {x}!"
    GET_OUTPUT_ITC: str = "r output itc!"
    SET_AUDIO_SOURCE: str = "s output audio {x}!"
    GET_AUDIO_SOURCE: str = "r output audio!"
    AUDIO_VOL_UP: str = "s output audio vol+!"
    AUDIO_VOL_DOWN: str = "s output audio vol-!"
    SET_AUDIO_VOL: str = "s output audio vol {x}!"
    GET_AUDIO_VOL: str = "r output audio vol!"
    SET_AUDIO_MUTE: str = "s output audio mute {x}!"
    GET_AUDIO_MUTE: str = "r output audio mute!"
    SET_AUTO_SWITCH: str = "s auto switch {x}!"
    GET_AUTO_SWITCH: str = "r auto switch!"
    SET_INPUT_SOURCE: str = "s in source {x}!"
    GET_INPUT_SOURCE: str = "r in source!"
    SET_MULTIVIEW: str = "s multiview {x}!"
    GET_MULTIVIEW: str = "r multiview!"
    SET_WINDOW_INPUT: str = "s window {x} in {y}!"
    GET_WINDOW_INPUT: str = "r window {x} in!"
    GET_ALL_WINDOWS_INPUT: str = "r window 0 in!"
    SET_PIP_POSITION: str = "s PIP position {x}!"
    GET_PIP_POSITION: str = "r PIP position!"
    SET_PIP_SIZE: str = "s PIP size {x}!"
    GET_PIP_SIZE: str = "r PIP size!"
    SET_PBP_MODE: str = "s PBP mode {x}!"
    GET_PBP_MODE: str = "r PBP mode!"
    SET_PBP_ASPECT: str = "s PBP aspect {x}!"
    GET_PBP_ASPECT: str = "r PBP aspect!"
    SET_TRIPLE_MODE: str = "s triple mode {x}!"
    GET_TRIPLE_MODE: str = "r triple mode!"
    SET_TRIPLE_ASPECT: str = "s triple aspect {x}!"
    GET_TRIPLE_ASPECT: str = "r triple aspect!"
    SET_QUAD_MODE: str = "s quad mode {x}!"
    GET_QUAD_MODE: str = "r quad mode!"
    SET_QUAD_ASPECT: str = "s quad aspect {x}!"
    GET_QUAD_ASPECT: str = "r quad aspect!"

    # --- HDS-only. Harmless to carry on both; the capability set gates use. ---
    # Border scope DIFFERS between models and the commands are not the same:
    # the UHD sets it per window, the HDS globally.
    SET_WINDOW_BORDER: str = "s window border {x}!"
    GET_WINDOW_BORDER: str = "r window border!"
    SET_WINDOW_BORDER_PER_WINDOW: str = "s window {x} border {y}!"
    GET_ALL_WINDOW_BORDERS: str = "r window 0 border!"
    SET_WINDOW_BORDER_COLOR: str = "s window {x} border color {y}!"
    GET_ALL_WINDOW_BORDER_COLORS: str = "r window 0 border color!"
    SET_SOURCE_OSD: str = "s window source osd {x}!"
    GET_SOURCE_OSD: str = "r window source osd!"

    capabilities: frozenset[str] = field(default_factory=frozenset)
    edid_options: tuple[str, ...] = ()
    resolution_options: tuple[str, ...] = ()
    pip_position_options: tuple[str, ...] = ()
    pip_size_options: tuple[str, ...] = ()
    quad_mode_options: tuple[str, ...] = ()
    # "window" = one border switch per window (UHD); "global" = a single
    # switch for all of them (HDS).
    border_scope: str = "global"
    # True when edid_options are the device's REAL mode names (so a reported
    # state will match one). False when they are positional placeholders,
    # in which case the real value is surfaced via a sensor instead.
    edid_options_verified: bool = False

    def supports(self, capability: str) -> bool:
        """True when this model has the capability at all."""
        return capability in self.capabilities


# The UHD is the base: its manual matches the historic command constants for
# everything except the system group, which the 0.3.4 change got wrong.
UHD_401MV = DeviceProfile(
    key="uhd401mv",
    model="UHD-401MV 4-port HDMI Multiviewer",
    # Unprefixed. The UHD's SYSTEM block is the ONLY unprefixed group in its
    # protocol -- every other setter takes `s `. Confirmed on hardware:
    # `power 1!` woke the unit, `s power 0!` did nothing for 14 hours.
    POWER_ON="power 1!",
    POWER_OFF="power 0!",
    REBOOT="reboot!",
    RESET="reset!",
    SET_INPUT_EDID="s input EDID {x}!",
    GET_INPUT_EDID="r input EDID!",
    # Window border, border colour and source OSD were wrongly modelled as
    # HDS-only: absent from the UHD manual, present in its firmware. `help!`
    # is authoritative; the manual is not.
    capabilities=frozenset(
        {
            CAP_VOLUME,
            CAP_HDCP,
            CAP_VKA,
            CAP_ITC,
            CAP_EDID,
            CAP_AUTO_SWITCH,
            CAP_WINDOW_BORDER,
            CAP_SOURCE_OSD,
        }
    ),
    edid_options=UHD_EDID_OPTIONS,
    edid_options_verified=True,
    resolution_options=UHD_RESOLUTION_OPTIONS,
    pip_position_options=PIP_POSITION_OPTIONS_UHD,
    pip_size_options=PIP_SIZE_OPTIONS_UHD,
    quad_mode_options=QUAD_MODE_OPTIONS_UHD,
    border_scope="window",
)

# The HDS prefixes its whole system group, and drops volume/HDCP/VKA/ITC
# entirely. Polling those on an HDS returns `E00` and publishing entities for
# them produces controls that cannot work -- which is exactly what the garage
# instance has been doing.
HDS_401MV = replace(
    UHD_401MV,
    key="hds401mv",
    model="HDS-401MV 4-port HDMI Multiviewer",
    POWER_ON="s power 1!",
    POWER_OFF="s power 0!",
    REBOOT="s reboot!",
    RESET="s reset!",
    SET_INPUT_EDID="s input edid {x}!",
    GET_INPUT_EDID="r input edid!",
    capabilities=frozenset(
        {
            CAP_EDID,
            CAP_AUTO_SWITCH,
            CAP_STATUS,
            CAP_WINDOW_BORDER,
            CAP_SOURCE_OSD,
        }
    ),
    edid_options=HDS_EDID_OPTIONS,
    # Placeholders. The HDS names its 7 modes nowhere, and the device reports
    # real names (`copy from hdmi out`) -- a valid value our list simply does
    # not contain. Learning them means cycling EDID, which renegotiates HDMI
    # for all four sources, so the real value is surfaced as a sensor instead.
    edid_options_verified=False,
    resolution_options=HDS_RESOLUTION_OPTIONS,
    pip_position_options=PIP_POSITION_OPTIONS,
    pip_size_options=PIP_SIZE_OPTIONS,
    quad_mode_options=LAYOUT_MODE_OPTIONS,
    border_scope="global",
)

PROFILES: dict[str, DeviceProfile] = {
    UHD_401MV.key: UHD_401MV,
    HDS_401MV.key: HDS_401MV,
}

DEFAULT_PROFILE_KEY = UHD_401MV.key


def get_profile(key: str) -> DeviceProfile:
    """Look up a profile by key, raising on an unknown one.

    Failing loudly is deliberate: a typo that silently fell back to a default
    would reintroduce the exact class of bug this module exists to prevent.
    """
    try:
        return PROFILES[key.strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown device_profile {key!r}; expected one of {sorted(PROFILES)}"
        ) from None
