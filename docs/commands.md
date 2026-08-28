# RS-232 command reference

Complete command sets for **both** multiviewers this proxy drives, with what
each command actually does.

The two devices are **not** command-compatible. Check the
[compatibility matrix](#compatibility-matrix) before assuming a command works
on both — that assumption caused a production regression (see
[Why this matters](#why-this-matters)).

**Sources.** Both from the devices' own `help!` output. The UHD's vendor manual
was the original source and proved **out of date** — see below.

!!! danger "The UHD manual disagrees with its firmware in nine places"

    `help!` on MCU **1.10.03**. Where they differ, the **firmware is right**:

    | command | manual | firmware |
    |---|---|---|
    | `s output res x!` | 1~14 | **1~15** |
    | `s input EDID x!` | 1~18 | **1~19** |
    | `s PIP position x!` | 1~4 | **1~5** |
    | `s PIP size x!` | 1~3 | **1~4** |
    | `s quad mode x!` | 1~2 | **1~3** |
    | `s window x border color y!` | absent | **present** (x=1~4, y=1~9) |
    | `s window x border y!` | absent | **present** (per window) |
    | `s window source osd x!` | absent | **present** |
    | `s edid user1 …!` | absent | **present** (custom EDID upload) |

    Three of those were wrongly modelled as HDS-only purely because the UHD
    manual omits them. And the border command is **not shared**: the UHD sets
    it per window, the HDS globally.

    Run `POST /api/raw {"command":"help!"}` against a unit before trusting any
    document, this one included.

!!! warning "`help!` reports the ACCEPT range, not the number of distinct values"

    Enumerated on hardware 2026-08-28 by setting each index and reading it back:

    | command | `help!` | distinct values | the extra slots |
    |---|---|---|---|
    | `s output res x!` | 1~15 | **15** | 15 = `AUTO` (inferred) |
    | `s input EDID x!` | 1~19 | **19** | 19 = `USER1` (confirmed) |
    | `s quad mode x!` | 1~3 | **2** | 3 reads back as `quad mode 2` |
    | `s PIP position x!` | 1~5 | **4** | 5 reads back as `right bottom` (= 4) |
    | `s PIP size x!` | 1~4 | **3** | 4 reads back as `large` (= 3) |

    Three of those five slots are aliases that clamp to the last real value.
    Trusting `help!`'s ranges alone would have shipped three controls that
    silently do nothing — the same class of error as trusting the manual, just
    from a better source. **Only set-and-read-back settles it.**

    Response wording also differs per model. Border colour is
    `window 1 border color yellow` on the HDS but `window 1 border color:` —
    colon, empty when unset — on the UHD.

## Protocol

| | |
|---|---|
| Baud | **115200** (default; the OSD also offers 57600 / 38400 / 19200 / 9600) |
| Framing | 8 data bits, 1 stop bit, no parity |
| Terminator | `!` — every command ends with it |
| Parameters | `x` = first parameter, `y` = second |
| Convention | `s ` = set, `r ` = read … **except where noted** |

The `s `/`r ` convention has exceptions, and they are the whole reason
profiles exist. On the UHD the entire SYSTEM group (`power`, `reboot`,
`reset`) is unprefixed; on the HDS it is prefixed like everything else.

## Compatibility matrix

| | UHD-401MV | HDS-401MV |
|---|---|---|
| power / reboot / reset | `power z!`, `reboot!`, `reset!` | `s power z!`, `s reboot!`, `s reset!` |
| input EDID | `s input EDID x!`, x=1~18 | `s input edid x!`, x=1~7 |
| output resolution | x=1~14 | x=1~4 |
| audio volume | yes | **absent** |
| output HDCP / VKA / ITC | yes | **absent** |
| `r status!` | absent | yes |
| window border / border colour | absent | yes |
| window source OSD | absent | yes |
| auto switch | yes | yes |
| multiview / windows / in source / PIP / PBP / triple / quad | identical | identical |

---

# UHD-401MV

## System

| Command | What it does |
|---|---|
| `help!` | Prints the device's own command list. The authoritative answer for any firmware — trust it over any document, including this one. |
| `r type!` | Returns `4x1 HDMI Multiviewer`. **Returns the same string on the HDS**, so it cannot identify which model you are talking to. |
| `r fw version!` | MCU and scaler firmware versions, on two lines. |
| `power z!` | z=0 standby, z=1 on. **Unprefixed** — `s power 0!` is not a command and is silently ignored. Power-on replies `power on` then runs an init sequence; allow **30–60 s** before the state settles. |
| `r power!` | `power on` or `power off`. Answers even in standby, so it is a reliable liveness probe. |
| `reboot!` | Restarts the device. Same init sequence as a power-on. |
| `reset!` | **Destructive.** Factory defaults — discards window layout, input mapping, EDID choice **and the serial baud rate**. Losing the baud rate means losing serial control until you fix it through the OSD. |

## Output

| Command | What it does |
|---|---|
| `s output res x!` | Output resolution, x=1~14 (table below). This is what the *display* receives; the scaler converts whatever the sources send. |
| `r output res!` | Current output resolution. |
| `s output hdcp x!` | Which HDCP version the output advertises: 1=HDCP 1.4, 2=HDCP 2.2, 3=off. Lower it when a display or downstream splitter refuses to handshake at 2.2; protected sources may then refuse to play. |
| `r output hdcp!` | Current HDCP mode. |
| `s output vka x!` | Video Keep Active pattern: 1=black, 2=blue. What the output shows when no valid source is present. Its purpose is to keep the HDMI link *up* so the display does not drop the signal and re-handshake — which is what causes the several-second black flash when a source sleeps. |
| `r output vka!` | Current VKA pattern. |
| `s output itc x!` | IT Content flag: 1=video mode, 2=PC mode. Tells the display how to treat the picture — video mode allows the display's video processing (smoothing, overscan); PC mode asks for 1:1 pixel mapping and usually lower latency. Set PC mode for text or gaming. |
| `r output itc!` | Current video/PC mode. |

### Resolution values (x=1~14)

| x | Resolution | | x | Resolution |
|---|---|---|---|---|
| 1 | 4096x2160p60 | | 8 | 1920x1080p60 |
| 2 | 4096x2160p50 | | 9 | 1920x1080p50 |
| 3 | 3840x2160p60 | | 10 | 1360x768p60 |
| 4 | 3840x2160p50 | | 11 | 1280x800p60 |
| 5 | 3840x2160p30 | | 12 | 1280x720p60 |
| 6 | 3840x2160p25 | | 13 | 1280x720p50 |
| 7 | 1920x1200p60RB | | 14 | 1024x768p60 |

## EDID

| Command | What it does |
|---|---|
| `s input EDID x!` | x=1~18 (table below). Sets the EDID the multiviewer presents **to all four sources** — the capability block telling them what resolutions and audio formats the sink accepts. Sources pick their output format from this. |
| `r input EDID!` | Current EDID mode. |

**EDID is the usual cause of "picture works, audio doesn't" and "one source is
black."** Advertise 7.1/Dolby and a source will send it; if the de-embedded
audio path cannot carry that stream you get silence. The analog and optical
outputs handle PCM 2.0 / Dolby Digital / DTS 5.1 and **do not support HBR
audio**, so an over-generous EDID produces a stream the unit cannot hand off.
Advertise 4K60 to four sources feeding a 1080p display and you spend bandwidth
on pixels the scaler discards.

Changing it renegotiates HDMI for every source at once, so a wrong value can
black the display or kill audio system-wide.

### EDID values (x=1~18)

| x | Mode | | x | Mode |
|---|---|---|---|---|
| 1 | 4K2K60_444, Stereo 2.0 | | 10 | 1920x1200, Stereo 2.0 |
| 2 | 4K2K60_444, Dolby/DTS 5.1 | | 11 | 1680x1050, Stereo 2.0 |
| 3 | 4K2K60_444, HD Audio 7.1 | | 12 | 1600x1200, Stereo 2.0 |
| 4 | 4K2K30_444, Stereo 2.0 | | 13 | 1440x900, Stereo 2.0 |
| 5 | 4K2K30_444, Dolby/DTS 5.1 | | 14 | 1360x768, Stereo 2.0 |
| 6 | 4K2K30_444, HD Audio 7.1 | | 15 | 1280x1024, Stereo 2.0 |
| 7 | 1080P, Stereo 2.0 | | 16 | 1024x768, Stereo 2.0 |
| 8 | 1080P, Dolby/DTS 5.1 | | 17 | 720p, Stereo 2.0 |
| 9 | 1080P, HD Audio 7.1 | | 18 | Copy from HDMI out |

Mode 18 passes through the real display's own EDID — usually the safest choice
when the display is the only sink.

## Audio

| Command | What it does |
|---|---|
| `s output audio x!` | Which input's audio is de-embedded to the analog/optical outputs. x=0 follows whatever window 1 is showing; x=1~4 pins it to a specific HDMI input regardless of what is on screen. |
| `r output audio!` | Current audio source. |
| `s output audio vol x!` | Absolute volume, x=0~100. Applies to LPCM only — bitstreamed Dolby/DTS passes through untouched. |
| `s output audio vol+!` | Step volume up one increment. |
| `s output audio vol-!` | Step volume down one increment. |
| `r output audio vol!` | Current volume. |
| `s output audio mute x!` | x=0 unmute, x=1 mute. |
| `r output audio mute!` | Current mute state. |

## Single-screen mode

| Command | What it does |
|---|---|
| `s auto switch x!` | x=0 disable, x=1 enable. When enabled, the device **automatically jumps to the next connected input** if the current source's signal disappears. Convenient standalone; hostile under automation — it is a second actor changing inputs underneath any scene that sets one explicitly. Sources that sleep (streaming sticks) will trigger it. |
| `r auto switch!` | Current auto-switch state. |
| `s in source x!` | Route input x=1~4 to the output in single-screen mode. |
| `r in source!` | Currently selected input. |

## Multiview

| Command | What it does |
|---|---|
| `s multiview x!` | Layout: 1=single, 2=PIP, 3=PBP, 4=triple, 5=quad. |
| `r multiview!` | Current layout. |
| `s window x in y!` | Put HDMI input y into window x (both 1~4). This is how a quad layout is assembled. |
| `r window x in!` | Which input is in window x; **x=0 returns all four**. |

### PIP

| Command | What it does |
|---|---|
| `s PIP position x!` | Inset corner: 1=top-left, 2=bottom-left, 3=top-right, 4=bottom-right. |
| `r PIP position!` | Current corner. |
| `s PIP size x!` | Inset size: 1=small, 2=medium, 3=large. |
| `r PIP size!` | Current size. |

### PBP / triple / quad

Each layout has a *mode* (which of two arrangements) and an *aspect*
(1=full screen — sources stretched to fill their tile; 2=16:9 — original
aspect preserved, pillarboxed).

| Command | What it does |
|---|---|
| `s PBP mode x!` / `r PBP mode!` | PBP arrangement, x=1~2. |
| `s PBP aspect x!` / `r PBP aspect!` | PBP tile aspect, x=1~2. |
| `s triple mode x!` / `r triple mode!` | Triple arrangement, x=1~2. |
| `s triple aspect x!` / `r triple aspect!` | Triple tile aspect, x=1~2. |
| `s quad mode x!` / `r quad mode!` | Quad arrangement, x=1~2. |
| `s quad aspect x!` / `r quad aspect!` | Quad tile aspect, x=1~2. |

---

# HDS-401MV

All 46 commands, as reported by the device's own `help!`. Everything shared
with the UHD behaves identically unless noted; only the differences are
explained again here.

## System

| Command | What it does |
|---|---|
| `help!` | The device's command list. |
| `r status!` | **HDS only.** A combined status dump, rather than querying each setting separately. |
| `r type!` | `4x1 HDMI Multiviewer` — same string the UHD returns. |
| `r fw version!` | MCU and scaler firmware. |
| `s power z!` | z=0~1. **Prefixed**, unlike the UHD. |
| `r power!` | Current power state; answers in standby. |
| `s reboot!` | **Prefixed.** Restart. |
| `s reset!` | **Prefixed. Destructive** — see the UHD `reset!` warning; it applies identically. |

## Output and EDID

| Command | What it does |
|---|---|
| `s output res x!` | Output resolution, **x=1~4 only** — a much smaller set than the UHD's 14. The device's own `help!` does not enumerate them and we have no HDS manual, so read back with `r output res!` to see what a value maps to. |
| `r output res!` | Current output resolution, e.g. `out resolution: 1920x1080p60`. |
| `s input edid x!` | **x=1~7 only**, and **lowercase `edid`**. Same meaning and same hazards as the UHD command. Mode labels are not documented anywhere available. |
| `r input edid!` | Current EDID mode. |

**No HDCP, VKA or ITC commands exist on this model.** Sending them returns an
error.

## Audio

| Command | What it does |
|---|---|
| `s output audio x!` | De-embedded audio source, x=0~4. Same semantics as the UHD. |
| `r output audio!` | Current audio source. |
| `s output audio mute x!` | x=0~1. |
| `r output audio mute!` | Current mute state. |

**No volume commands exist on this model** — no `vol`, `vol+` or `vol-`.
Volume must be handled downstream (an AVR, or the Sonos the audio feeds).
Querying volume here returns `E00`.

## Single-screen mode

| Command | What it does |
|---|---|
| `s auto switch x!` / `r auto switch!` | Automatic input failover, x=0~1. Identical to the UHD. |
| `s in source x!` / `r in source!` | Route input x=1~4 in single-screen mode. |

## Multiview

| Command | What it does |
|---|---|
| `s multiview x!` / `r multiview!` | Layout 1~5: single, PIP, PBP, triple, quad. |
| `s window x in y!` | Put input y into window x. |
| `r window x in!` | Window x's input; x=0 returns all. |

Windows can only be assigned while a multiview layout is active. Sending
window commands in single-screen mode returns
`can't set by pc! please switch to multi-viewer mode first!`.

### Window borders and OSD — HDS only

| Command | What it does |
|---|---|
| `s window border y!` | y=0~1. Master switch for drawing borders around every window — useful for telling adjacent tiles apart in quad. |
| `r window border!` | Current border mode. |
| `s window x border color y!` | Border colour of window x (1~4), y=1~9. Lets each tile be identified by colour. |
| `r window x border color!` | Border colour; x=0 returns all four. |
| `s window source osd x!` | x=0~1. Overlays each window with a label naming its source, so you can see which input is in which tile. |
| `r window source osd!` | Current source-OSD state. |

### PIP / PBP / triple / quad

Identical to the UHD, but **lowercase** in the device's own listing
(`s pip position x!`, `s pbp mode x!`). Uppercase forms are what the proxy has
always sent to this device and they work, so the parser appears
case-insensitive — but the lowercase forms above are what `help!` reports.

| Command | Values |
|---|---|
| `s pip position x!` / `r pip position!` | x=1~4 |
| `s pip size x!` / `r pip size!` | x=1~3 |
| `s pbp mode x!` / `r pbp mode!` | x=1~2 |
| `s pbp aspect x!` / `r pbp aspect!` | x=1~2 |
| `s triple mode x!` / `r triple mode!` | x=1~2 |
| `s triple aspect x!` / `r triple aspect!` | x=1~2 |
| `s quad mode x!` / `r quad mode!` | x=1~2 |
| `s quad aspect x!` / `r quad aspect!` | x=1~2 |

---

## Device profiles

`DEVICE_PROFILE` (chart value `deviceProfile`) selects which model an instance
drives: `uhd401mv` or `hds401mv`.

It **cannot** be auto-detected — `r type!` returns `4x1 HDMI Multiviewer` on
both — so it is explicit configuration, and an unknown value raises at startup
rather than falling back to a default.

A profile gates three things:

1. **Command strings** — the power/reboot/reset prefix and the EDID keyword case.
2. **Capabilities** — polling *and* HA discovery. The proxy never queries a
   command the model lacks (which returns `E00` every cycle) and never
   publishes an entity that cannot work.
3. **Parameter domains** — EDID option lists (18 vs 7) and their labels.

### Why this matters

Release **0.3.4** changed power to `s power z!`. That is correct for the HDS
and made its power switch work for the first time. Applied to a UHD it
**breaks** power control entirely: the unit silently ignores the command — no
error, no state change, nothing in the log. It was reverted after ~14 hours.

Two things made it hard to spot. The command is accepted at the serial layer
and simply not acted on, so the proxy reports success. And a commanded power
change takes **30–60 s** to appear in the state, so checking a few seconds
later reads the old value and looks like the same failure.

## What the proxy exposes

Control is **MQTT** (discovery entities plus command/state topics). The REST
API is internal and used for diagnostics only.

As of **0.5.0 every settable command is exposed** except two:

- **`reset`** — deliberately never published. It discards the serial baud rate
  along with the layout, which costs all serial control until it is corrected
  through the OSD. Reachable on the REST API only.
- **`r status!`** — a combined dump of values the poller already reads
  individually, so it would be a redundant sensor rather than a control.

One partial: the **HDS output resolution** accepts x=1~4 but names those values
nowhere, and the device reports real resolution strings (`1920x1080p60`). An
index-labelled select would publish a state matching no option, so the HDS keeps
its read-only resolution *sensor* until the four names are captured. The UHD
gets a full 14-option select.

Similarly, the UHD may report `AUTO`, which is not settable over RS-232. The
resolution **sensor** always shows the device's truth including `AUTO`; the
**select** offers only the 14 values that can actually be set, and publishes no
state while the device is on `AUTO`.

## Asking the device directly

`POST /api/raw` sends a **read-only** raw command and returns the verbatim
reply. The allowlist accepts `help!` and anything starting with `r `; every
setter — `reboot` and `reset` included — is refused rather than forwarded, so
the endpoint cannot change device state. It is REST-only and never published
over MQTT.

```bash
curl -s -X POST http://hdmi-multiviewer-proxy:8080/api/raw \
  -H 'Content-Type: application/json' \
  -d '{"command":"help!"}'
```

**`help!` is the authoritative answer to any protocol question** — it lists the
device's own command set with parameter ranges, which is how the HDS's 46
commands in this document were obtained. Use it in preference to this file or
any manual when the two disagree; firmware wins.

It exists because a unit whose serial line the proxy owns exclusively is
otherwise uninterrogable. The HDS could be reached over its ESPHome TCP bridge;
the UHD could not be reached at all.
