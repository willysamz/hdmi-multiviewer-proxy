# MViewer Proxy

Proxy for controlling OREI 4x1 HDMI multiviewers over RS-232, publishing them
to Home Assistant via MQTT.

Supports two models, selected with `DEVICE_PROFILE` (`uhd401mv` or
`hds401mv`). **They are not command-compatible** — the UHD takes `power z!`
while the HDS takes `s power z!`, and the HDS has no volume/HDCP/VKA/ITC
commands at all. `r type!` returns the same string on both, so the model
cannot be auto-detected and must be declared. See the
[RS-232 command reference](docs/commands.md) for the complete set per device.

## Features

- Full RS-232 command support for the UHD-401MV and HDS-401MV
- Home Assistant MQTT discovery — the primary control surface
- Capability-gated entities: a model only gets controls it can actually perform
- REST API with OpenAPI documentation (internal / diagnostics)
- Kubernetes-ready with Helm chart
- Automatic reconnection with exponential backoff
- Health endpoints for liveness/readiness probes

## Quick Start

### Using Docker

```bash
docker run -d \
  --name hdmi-multiviewer-proxy \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  -p 8080:8080 \
  ghcr.io/willysamz/hdmi-multiviewer-proxy:latest
```

### Using Helm

```bash
# Add the Helm repository
helm repo add hdmi-multiviewer-proxy https://willysamz.github.io/hdmi-multiviewer-proxy
helm repo update

# Install the chart
helm install mviewer hdmi-multiviewer-proxy/hdmi-multiviewer-proxy \
  --set nodeSelector."kubernetes\.io/hostname"=<node-with-usb-device>
```

Or install directly from the Git repository:

```bash
helm install mviewer ./chart \
  --set nodeSelector."kubernetes\.io/hostname"=<node-with-usb-device>
```

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `SERIAL_PORT` | Serial port path | `/dev/ttyUSB0` |
| `SERIAL_BAUD_RATE` | Baud rate | `115200` |
| `SERIAL_TIMEOUT` | Command timeout (seconds) | `2.0` |
| `SERIAL_HEARTBEAT_INTERVAL` | Heartbeat interval (seconds) | `30` |
| `SERVER_PORT` | HTTP server port | `8080` |
| `LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `LOG_JSON` | Output logs as JSON | `true` |

## API Endpoints

Once running, visit `http://localhost:8080/docs` for interactive API documentation.

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz/live` | GET | Liveness probe |
| `/healthz/ready` | GET | Readiness probe |
| `/api/status` | GET | Device status and connection state |
| `/api/power` | POST | Power on/off |
| `/api/multiview` | GET/POST | Display mode (single/PIP/PBP/triple/quad) |
| `/api/windows/{id}/input` | POST | Set window input source |
| `/api/audio` | GET | Audio settings |
| `/api/audio/source` | POST | Set audio source |
| `/api/audio/volume` | POST | Set volume (0-100) |
| `/api/audio/mute` | POST | Mute/unmute |

## Home Assistant Integration

See [docs/home-assistant.md](docs/home-assistant.md) for detailed integration instructions.

Quick example:

```yaml
rest_command:
  mviewer_set_mode:
    url: http://hdmi-multiviewer-proxy:8080/api/multiview
    method: POST
    content_type: application/json
    payload: '{"mode": "{{ mode }}"}'
```

## Development

```bash
# Install dependencies
make install

# Run development server
make dev

# Run tests
make test

# Lint code
make lint
```

## Documentation

- [RS-232 Command Reference](docs/commands.md)
- [Home Assistant Integration](docs/home-assistant.md)
- [OpenAPI Specification](docs/openapi.json)

## License

MIT
