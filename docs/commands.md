# UHD-401MV RS-232 Command Reference

Serial port settings: **115200 baud, 8 data bits, 1 stop bit, no parity**

Command format: `command!` (terminated with `!`)

Parameters: `x` = Parameter 1, `y` = Parameter 2

---

## System Commands

| Command | Description | Example | Response |
|---------|-------------|---------|----------|
| `help!` | List all commands | `help!` | Command list |
| `r type!` | Get device model | `r type!` | `4x1 HDMI Multiviewer` |
| `r fw version!` | Get firmware version | `r fw version!` | `MCU FW version x.xx.xx`<br>`SCALER FW version x.xx.xx` |
| `power 1!` | Power on | `power 1!` | `power on`<br>`System Initializing...`<br>`Initialization Finished!` |
| `power 0!` | Power off | `power 0!` | `power off` |
| `r power!` | Get power state | `r power!` | `power on` or `power off` |
| `reboot!` | Reboot device | `reboot!` | `Reboot...`<br>`System Initializing...` |
| `reset!` | Factory reset | `reset!` | `Reset to factory defaults` |

---

## Output Settings

| Command | Description | Values | Response |
|---------|-------------|--------|----------|
| `s output res x!` | Set resolution | 1-14 (see table below) | `out resolution: 3840x2160p60` |
| `r output res!` | Get resolution | - | `out resolution: 3840x2160p60` |
| `s output hdcp x!` | Set HDCP mode | 1=HDCP 1.4, 2=HDCP 2.2, 3=OFF | `output HDCP: HDCP 1.4` |
| `r output hdcp!` | Get HDCP mode | - | `output HDCP: HDCP 1.4` |
| `s output vka x!` | Set keep-active pattern | 1=black, 2=blue | `output VKA pattern: black screen` |
| `r output vka!` | Get keep-active pattern | - | `output VKA pattern: black screen` |
| `s output itc x!` | Set video mode | 1=video, 2=PC | `output ITC: video mode` |
| `r output itc!` | Get video mode | - | `output ITC: video mode` |

### Resolution Values

| Value | Resolution |
|-------|------------|
| 1 | 4096x2160p60 |
| 2 | 4096x2160p50 |
| 3 | 3840x2160p60 |
| 4 | 3840x2160p50 |
| 5 | 3840x2160p30 |
| 6 | 3840x2160p25 |
| 7 | 1920x1200p60RB |
| 8 | 1920x1080p60 |
| 9 | 1920x1080p50 |
| 10 | 1360x768p60 |
| 11 | 1280x800p60 |
| 12 | 1280x720p60 |
| 13 | 1280x720p50 |
| 14 | 1024x768p60 |

---

## EDID Settings

| Command | Description | Values | Response |
|---------|-------------|--------|----------|
| `s input EDID x!` | Set input EDID | 1-18 (see table below) | `input EDID: 4K2K60_444,Stereo Audio 2.0` |
| `r input EDID!` | Get input EDID | - | `input EDID: 4K2K60_444,Stereo Audio 2.0` |

### EDID Values

| Value | EDID Mode |
|-------|-----------|
| 1 | 4K2K60_444, Stereo Audio 2.0 |
| 2 | 4K2K60_444, Dolby/DTS 5.1 |
| 3 | 4K2K60_444, HD Audio 7.1 |
| 4 | 4K2K30_444, Stereo Audio 2.0 |
| 5 | 4K2K30_444, Dolby/DTS 5.1 |
| 6 | 4K2K30_444, HD Audio 7.1 |
| 7 | 1080P, Stereo Audio 2.0 |
| 8 | 1080P, Dolby/DTS 5.1 |
| 9 | 1080P, HD Audio 7.1 |
| 10 | 1920x1200, Stereo Audio 2.0 |
| 11 | 1680x1050, Stereo Audio 2.0 |
| 12 | 1600x1200, Stereo Audio 2.0 |
| 13 | 1440x900, Stereo Audio 2.0 |
| 14 | 1360x768, Stereo Audio 2.0 |
| 15 | 1280x1024, Stereo Audio 2.0 |
| 16 | 1024x768, Stereo Audio 2.0 |
| 17 | 720p, Stereo Audio 2.0 |
| 18 | Copy from HDMI out |

---

## Audio Settings

| Command | Description | Values | Response |
|---------|-------------|--------|----------|
| `s output audio x!` | Set audio source | 0-4 (see below) | `output audio: HDMI 1 input audio` |
| `r output audio!` | Get audio source | - | `output audio: follow window 1 selected source` |
| `s output audio vol+!` | Volume up | - | `output audio volume: 50` |
| `s output audio vol-!` | Volume down | - | `output audio volume: 50` |
| `s output audio vol x!` | Set volume | 0-100 | `output audio volume: 30` |
| `r output audio vol!` | Get volume | - | `output audio volume: 30` |
| `s output audio mute x!` | Set mute | 0=off, 1=on | `output audio mute: off` |
| `r output audio mute!` | Get mute state | - | `output audio mute: off` |

### Audio Source Values

| Value | Source |
|-------|--------|
| 0 | Follow window 1 selected source |
| 1 | HDMI 1 input audio |
| 2 | HDMI 2 input audio |
| 3 | HDMI 3 input audio |
| 4 | HDMI 4 input audio |

---

## Single Screen Mode

| Command | Description | Values | Response |
|---------|-------------|--------|----------|
| `s auto switch x!` | Enable/disable auto switch | 0=off, 1=on | `auto switch off` |
| `r auto switch!` | Get auto switch state | - | `auto switch off` |
| `s in source x!` | Set input source | 1-4 (HDMI 1-4) | `HDMI 1` |
| `r in source!` | Get input source | - | `HDMI 1` |

---

## Multiview Mode

| Command | Description | Values | Response |
|---------|-------------|--------|----------|
| `s multiview x!` | Set display mode | 1-5 (see below) | `single screen` |
| `r multiview!` | Get display mode | - | `single screen` |
| `s window x in y!` | Set window input | x=1-4 (window), y=1-4 (HDMI) | `window 1 select HDMI 1` |
| `r window x in!` | Get window input | x=0-4 (0=all) | `window 1 select HDMI 1` |

### Multiview Mode Values

| Value | Mode |
|-------|------|
| 1 | Single screen |
| 2 | PIP (Picture-in-Picture) |
| 3 | PBP (Picture-by-Picture) |
| 4 | Triple screen |
| 5 | Quad screen |

---

## PIP Settings

| Command | Description | Values | Response |
|---------|-------------|--------|----------|
| `s PIP position x!` | Set PIP position | 1-4 (see below) | `PIP on right top` |
| `r PIP position!` | Get PIP position | - | `PIP on right top` |
| `s PIP size x!` | Set PIP size | 1=small, 2=middle, 3=large | `PIP size: large` |
| `r PIP size!` | Get PIP size | - | `PIP size: large` |

### PIP Position Values

| Value | Position |
|-------|----------|
| 1 | Left Top |
| 2 | Left Bottom |
| 3 | Right Top |
| 4 | Right Bottom |

---

## PBP Settings

| Command | Description | Values | Response |
|---------|-------------|--------|----------|
| `s PBP mode x!` | Set PBP mode | 1=mode 1, 2=mode 2 | `PBP mode 1` |
| `r PBP mode!` | Get PBP mode | - | `PBP mode 1` |
| `s PBP aspect x!` | Set PBP aspect | 1=full, 2=16:9 | `PBP aspect: full screen` |
| `r PBP aspect!` | Get PBP aspect | - | `PBP aspect: full screen` |

---

## Triple Screen Settings

| Command | Description | Values | Response |
|---------|-------------|--------|----------|
| `s triple mode x!` | Set triple mode | 1=mode 1, 2=mode 2 | `triple mode 1` |
| `r triple mode!` | Get triple mode | - | `triple mode 1` |
| `s triple aspect x!` | Set triple aspect | 1=full, 2=16:9 | `triple aspect: full screen` |
| `r triple aspect!` | Get triple aspect | - | `triple aspect: full screen` |

---

## Quad Screen Settings

| Command | Description | Values | Response |
|---------|-------------|--------|----------|
| `s quad mode x!` | Set quad mode | 1=mode 1, 2=mode 2 | `quad mode 1` |
| `r quad mode!` | Get quad mode | - | `quad mode 1` |
| `s quad aspect x!` | Set quad aspect | 1=full, 2=16:9 | `quad aspect: full screen` |
| `r quad aspect!` | Get quad aspect | - | `quad aspect: full screen` |
