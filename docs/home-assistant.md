# Home Assistant Integration

This guide explains how to integrate the Multiviewer Serial Proxy with Home Assistant using the RESTful integration.

## Prerequisites

- Multiviewer Serial Proxy running and accessible from Home Assistant
- Service URL (e.g., `http://hdmi-multiviewer-proxy:8080` or `http://192.168.1.100:8080`)

## Configuration

Add the following to your `configuration.yaml`:

### Sensors (Read State)

```yaml
rest:
  # Device status and connection
  - resource: http://hdmi-multiviewer-proxy:8080/api/status
    scan_interval: 30
    sensor:
      - name: "Multiviewer Connection"
        value_template: "{{ value_json.connection }}"
        icon: mdi:connection
    binary_sensor:
      - name: "Multiviewer Connected"
        value_template: "{{ value_json.connection != 'unavailable' }}"
        device_class: connectivity

  # Audio settings
  - resource: http://hdmi-multiviewer-proxy:8080/api/audio
    scan_interval: 30
    sensor:
      - name: "Multiviewer Audio Source"
        value_template: "{{ value_json.source_name }}"
        icon: mdi:speaker
      - name: "Multiviewer Volume"
        value_template: "{{ value_json.volume }}"
        icon: mdi:volume-high
        unit_of_measurement: "%"
    binary_sensor:
      - name: "Multiviewer Muted"
        value_template: "{{ value_json.muted }}"
        device_class: sound

  # Display mode
  - resource: http://hdmi-multiviewer-proxy:8080/api/multiview
    scan_interval: 30
    sensor:
      - name: "Multiviewer Mode"
        value_template: "{{ value_json.mode }}"
        icon: mdi:monitor

  # Window inputs
  - resource: http://hdmi-multiviewer-proxy:8080/api/windows
    scan_interval: 30
    sensor:
      - name: "Multiviewer Window 1"
        value_template: "{{ value_json.windows[0].input_name }}"
        icon: mdi:monitor-screenshot
      - name: "Multiviewer Window 2"
        value_template: "{{ value_json.windows[1].input_name }}"
        icon: mdi:monitor-screenshot
      - name: "Multiviewer Window 3"
        value_template: "{{ value_json.windows[2].input_name }}"
        icon: mdi:monitor-screenshot
      - name: "Multiviewer Window 4"
        value_template: "{{ value_json.windows[3].input_name }}"
        icon: mdi:monitor-screenshot

  # Output settings
  - resource: http://hdmi-multiviewer-proxy:8080/api/output
    scan_interval: 60
    sensor:
      - name: "Multiviewer Resolution"
        value_template: "{{ value_json.resolution }}"
        icon: mdi:monitor-shimmer
```

### Commands (Control Device)

```yaml
rest_command:
  # Power control
  multiviewer_power_on:
    url: http://hdmi-multiviewer-proxy:8080/api/power
    method: POST
    content_type: application/json
    payload: '{"power": true}'

  multiviewer_power_off:
    url: http://hdmi-multiviewer-proxy:8080/api/power
    method: POST
    content_type: application/json
    payload: '{"power": false}'

  # Display mode
  multiviewer_set_mode:
    url: http://hdmi-multiviewer-proxy:8080/api/multiview
    method: POST
    content_type: application/json
    payload: '{"mode": "{{ mode }}"}'

  # Window input routing
  multiviewer_set_window_input:
    url: "http://hdmi-multiviewer-proxy:8080/api/windows/{{ window }}/input"
    method: POST
    content_type: application/json
    payload: '{"input": {{ input }}}'

  # Audio source
  multiviewer_set_audio_source:
    url: http://hdmi-multiviewer-proxy:8080/api/audio/source
    method: POST
    content_type: application/json
    payload: '{"source": {{ source }}}'

  # Volume
  multiviewer_set_volume:
    url: http://hdmi-multiviewer-proxy:8080/api/audio/volume
    method: POST
    content_type: application/json
    payload: '{"volume": {{ volume }}}'

  multiviewer_volume_up:
    url: http://hdmi-multiviewer-proxy:8080/api/audio/volume/up
    method: POST

  multiviewer_volume_down:
    url: http://hdmi-multiviewer-proxy:8080/api/audio/volume/down
    method: POST

  # Mute
  multiviewer_mute:
    url: http://hdmi-multiviewer-proxy:8080/api/audio/mute
    method: POST
    content_type: application/json
    payload: '{"muted": true}'

  multiviewer_unmute:
    url: http://hdmi-multiviewer-proxy:8080/api/audio/mute
    method: POST
    content_type: application/json
    payload: '{"muted": false}'

  multiviewer_toggle_mute:
    url: http://hdmi-multiviewer-proxy:8080/api/audio/mute/toggle
    method: POST

  # PIP settings
  multiviewer_set_pip:
    url: http://hdmi-multiviewer-proxy:8080/api/pip
    method: POST
    content_type: application/json
    payload: '{"position": {{ position }}, "size": {{ size }}}'
```

## Helper Entities

Create input helpers for easier control:

```yaml
input_select:
  multiviewer_mode:
    name: "Multiviewer Mode"
    options:
      - single
      - pip
      - pbp
      - triple
      - quad
    icon: mdi:monitor

  multiviewer_audio_source:
    name: "Multiviewer Audio"
    options:
      - "Follow Window 1"
      - "HDMI 1"
      - "HDMI 2"
      - "HDMI 3"
      - "HDMI 4"
    icon: mdi:speaker

input_number:
  multiviewer_volume:
    name: "Multiviewer Volume"
    min: 0
    max: 100
    step: 5
    icon: mdi:volume-high
    unit_of_measurement: "%"
```

## Automations

### Sync Input Helpers with Device

```yaml
automation:
  # Sync mode selection to device
  - alias: "Multiviewer: Set Mode"
    trigger:
      - platform: state
        entity_id: input_select.multiviewer_mode
    condition:
      - condition: state
        entity_id: binary_sensor.multiviewer_connected
        state: "on"
    action:
      - service: rest_command.multiviewer_set_mode
        data:
          mode: "{{ states('input_select.multiviewer_mode') }}"

  # Sync audio source selection to device
  - alias: "Multiviewer: Set Audio Source"
    trigger:
      - platform: state
        entity_id: input_select.multiviewer_audio_source
    condition:
      - condition: state
        entity_id: binary_sensor.multiviewer_connected
        state: "on"
    action:
      - service: rest_command.multiviewer_set_audio_source
        data:
          source: >
            {% set mapping = {
              "Follow Window 1": 0,
              "HDMI 1": 1,
              "HDMI 2": 2,
              "HDMI 3": 3,
              "HDMI 4": 4
            } %}
            {{ mapping[states('input_select.multiviewer_audio_source')] }}

  # Sync volume slider to device
  - alias: "Multiviewer: Set Volume"
    trigger:
      - platform: state
        entity_id: input_number.multiviewer_volume
    condition:
      - condition: state
        entity_id: binary_sensor.multiviewer_connected
        state: "on"
    action:
      - service: rest_command.multiviewer_set_volume
        data:
          volume: "{{ states('input_number.multiviewer_volume') | int }}"
```

## Scenes

Create scenes to save and restore complete configurations:

```yaml
scene:
  - name: "Gaming Setup"
    entities:
      input_select.multiviewer_mode:
        state: "pip"
      input_select.multiviewer_audio_source:
        state: "HDMI 1"
    # Additional actions via script
    
  - name: "Movie Night"
    entities:
      input_select.multiviewer_mode:
        state: "single"
      input_select.multiviewer_audio_source:
        state: "HDMI 2"

  - name: "Work Mode"
    entities:
      input_select.multiviewer_mode:
        state: "quad"
      input_select.multiviewer_audio_source:
        state: "Follow Window 1"
```

### Scene Scripts with Window Configuration

For more complex scenes that set window inputs:

```yaml
script:
  gaming_setup:
    alias: "Gaming Setup"
    sequence:
      - service: rest_command.multiviewer_set_mode
        data:
          mode: "pip"
      - delay:
          milliseconds: 500
      - service: rest_command.multiviewer_set_window_input
        data:
          window: 1
          input: 1  # PC on main
      - service: rest_command.multiviewer_set_window_input
        data:
          window: 2
          input: 3  # Console in PIP
      - service: rest_command.multiviewer_set_audio_source
        data:
          source: 1  # Audio from PC

  movie_night:
    alias: "Movie Night"
    sequence:
      - service: rest_command.multiviewer_set_mode
        data:
          mode: "single"
      - delay:
          milliseconds: 500
      - service: rest_command.multiviewer_set_window_input
        data:
          window: 1
          input: 2  # Apple TV / Streaming box
      - service: rest_command.multiviewer_set_audio_source
        data:
          source: 2

  work_quad_view:
    alias: "Work Quad View"
    sequence:
      - service: rest_command.multiviewer_set_mode
        data:
          mode: "quad"
      - delay:
          milliseconds: 500
      - service: rest_command.multiviewer_set_window_input
        data:
          window: 1
          input: 1
      - service: rest_command.multiviewer_set_window_input
        data:
          window: 2
          input: 2
      - service: rest_command.multiviewer_set_window_input
        data:
          window: 3
          input: 3
      - service: rest_command.multiviewer_set_window_input
        data:
          window: 4
          input: 4
      - service: rest_command.multiviewer_set_audio_source
        data:
          source: 0  # Follow window 1
```

## Dashboard Card

Example Lovelace card for controlling the multiviewer:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Multiviewer
    entities:
      - entity: binary_sensor.multiviewer_connected
        name: Connection
      - entity: sensor.multiviewer_mode
        name: Current Mode
      - entity: input_select.multiviewer_mode
        name: Set Mode
      - type: divider
      - entity: sensor.multiviewer_audio_source
        name: Audio Source
      - entity: input_select.multiviewer_audio_source
        name: Set Audio
      - entity: sensor.multiviewer_volume
        name: Volume
      - entity: binary_sensor.multiviewer_muted
        name: Muted

  - type: horizontal-stack
    cards:
      - type: button
        name: Gaming
        icon: mdi:gamepad-variant
        tap_action:
          action: call-service
          service: script.gaming_setup

      - type: button
        name: Movie
        icon: mdi:movie
        tap_action:
          action: call-service
          service: script.movie_night

      - type: button
        name: Work
        icon: mdi:briefcase
        tap_action:
          action: call-service
          service: script.work_quad_view

  - type: glance
    title: Window Inputs
    entities:
      - entity: sensor.multiviewer_window_1
        name: Win 1
      - entity: sensor.multiviewer_window_2
        name: Win 2
      - entity: sensor.multiviewer_window_3
        name: Win 3
      - entity: sensor.multiviewer_window_4
        name: Win 4
```

## Time-Based Automations

```yaml
automation:
  - alias: "Multiviewer: Morning Work Mode"
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
      - condition: state
        entity_id: binary_sensor.multiviewer_connected
        state: "on"
    action:
      - service: script.work_quad_view

  - alias: "Multiviewer: Evening Entertainment"
    trigger:
      - platform: time
        at: "18:00:00"
    condition:
      - condition: state
        entity_id: binary_sensor.multiviewer_connected
        state: "on"
    action:
      - service: script.movie_night

  - alias: "Multiviewer: Power Off at Night"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: rest_command.multiviewer_power_off
```

## Voice Control

Once configured, you can use voice assistants:

- *"Hey Google, run Gaming Setup"*
- *"Alexa, activate Movie Night"*
- *"Hey Siri, turn on Work Mode"*

## Troubleshooting

### Device Shows Unavailable

1. Check if the proxy service is running
2. Verify the USB serial device is connected
3. Check proxy logs: `kubectl logs -l app.kubernetes.io/name=hdmi-multiviewer-proxy`

### Commands Not Working

1. Verify the device is powered on (check `sensor.multiviewer_connection`)
2. Check Home Assistant logs for REST command errors
3. Test the API directly: `curl http://hdmi-multiviewer-proxy:8080/api/status`

### Slow Response

The proxy caches device state. If you need real-time updates, reduce `scan_interval` in the REST sensor configuration (not recommended below 10 seconds).

## Parameter Reference

### Display Modes
| Mode | Description |
|------|-------------|
| `single` | Single full-screen input |
| `pip` | Picture-in-picture |
| `pbp` | Picture-by-picture (side by side) |
| `triple` | Three windows |
| `quad` | Four windows |

### Audio Sources
| Value | Source |
|-------|--------|
| 0 | Follow window 1 |
| 1 | HDMI 1 |
| 2 | HDMI 2 |
| 3 | HDMI 3 |
| 4 | HDMI 4 |

### Window/Input IDs
| ID | Description |
|----|-------------|
| 1 | Window 1 / HDMI 1 |
| 2 | Window 2 / HDMI 2 |
| 3 | Window 3 / HDMI 3 |
| 4 | Window 4 / HDMI 4 |

### PIP Position
| Value | Position |
|-------|----------|
| 1 | Top Left |
| 2 | Bottom Left |
| 3 | Top Right |
| 4 | Bottom Right |

### PIP Size
| Value | Size |
|-------|------|
| 1 | Small |
| 2 | Medium |
| 3 | Large |
