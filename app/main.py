"""FastAPI application entry point."""

import asyncio
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI

from app import __version__
from app.config import settings
from app.controller import Controller, ControllerError
from app.dependencies import set_serial_handler, set_startup_time
from app.mqtt_client import MqttClient
from app.poller import Poller
from app.profiles import CAP_AUTO_SWITCH, CAP_EDID
from app.routers import audio, display, health, output, system
from app.serial_handler import SerialHandler

# Configure structured logging
LOG_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_renderer = (
    structlog.processors.JSONRenderer() if settings.log_json else structlog.dev.ConsoleRenderer()
)
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _renderer,  # type: ignore[list-item]
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        LOG_LEVELS.get(settings.log_level.upper(), 20)
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    v0.2+: alongside the existing serial handler, optionally bring up an
    MQTT session, a state-polling task that publishes to MQTT, and a
    command-topic subscriber that translates HA select/switch/number
    actions back into serial commands.
    """
    set_startup_time(datetime.now(UTC))
    log.info(
        "starting_application",
        version=__version__,
        port=settings.server_port,
        mqtt_enabled=settings.mqtt_enabled,
    )

    serial_handler = SerialHandler(
        port=settings.serial_port,
        baud_rate=settings.serial_baud_rate,
        timeout=settings.serial_timeout,
        heartbeat_interval=settings.serial_heartbeat_interval,
        reconnect_backoff_max=settings.serial_reconnect_backoff_max,
    )
    set_serial_handler(serial_handler)
    await serial_handler.start()

    # MQTT path is opt-in. Without it the proxy behaves like v0.1.x.
    mqtt_ctx = None
    poller: Poller | None = None
    command_task: asyncio.Task | None = None

    if settings.mqtt_enabled:
        mqtt = MqttClient(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            username=settings.mqtt_username,
            password=settings.mqtt_password,
            client_id=settings.mqtt_client_id,
            keepalive=settings.mqtt_keepalive,
            qos=settings.mqtt_qos,
            availability_topic=f"{settings.mqtt_topic_prefix.strip('/')}/bridge/available",
        )
        poller = Poller(serial=serial_handler, mqtt=mqtt, settings=settings)
        controller = Controller(serial=serial_handler, mqtt=mqtt, poller=poller, settings=settings)

        mqtt_ctx = mqtt.session()
        await mqtt_ctx.__aenter__()
        await poller.start()
        command_task = asyncio.create_task(
            _command_subscriber(mqtt, controller, settings.mqtt_topic_prefix)
        )

    try:
        yield
    finally:
        log.info("shutting_down_application")
        if command_task is not None:
            command_task.cancel()
        if poller is not None:
            await poller.stop()
        if mqtt_ctx is not None:
            await mqtt_ctx.__aexit__(None, None, None)
        await serial_handler.stop()


# Regexes for parsing command topics — anchored on the topic-prefix wildcard.
_POWER_SET_RE = re.compile(r"^[^/]+/power/set$")
_MODE_SET_RE = re.compile(r"^[^/]+/mode/set$")
_WINDOW_SET_RE = re.compile(r"^[^/]+/windows/(?P<n>\d+)/set$")
_INPUT_SOURCE_SET_RE = re.compile(r"^[^/]+/input/source/set$")
_AUDIO_SOURCE_SET_RE = re.compile(r"^[^/]+/audio/source/set$")
_AUDIO_VOLUME_SET_RE = re.compile(r"^[^/]+/audio/volume/set$")
_AUDIO_MUTED_SET_RE = re.compile(r"^[^/]+/audio/muted/set$")
_PIP_POSITION_SET_RE = re.compile(r"^[^/]+/pip/position/set$")
_PIP_SIZE_SET_RE = re.compile(r"^[^/]+/pip/size/set$")
_AUTO_SWITCH_SET_RE = re.compile(r"^[^/]+/auto_switch/set$")
_EDID_SET_RE = re.compile(r"^[^/]+/edid/set$")


async def _command_subscriber(mqtt: MqttClient, controller: Controller, topic_prefix: str) -> None:
    """Subscribe to every command topic and route to the Controller."""
    prefix = topic_prefix.strip("/")
    # Subscribe to the per-category wildcards. Order doesn't matter; the
    # routing logic below disambiguates by regex match.
    for sub in [
        f"{prefix}/power/set",
        f"{prefix}/mode/set",
        f"{prefix}/windows/+/set",
        f"{prefix}/input/source/set",
        f"{prefix}/audio/source/set",
        f"{prefix}/audio/volume/set",
        f"{prefix}/audio/muted/set",
        f"{prefix}/pip/position/set",
        f"{prefix}/pip/size/set",
    ]:
        await mqtt.subscribe(sub)
    # Capability-gated topics: subscribing to a command this model cannot
    # perform would leave HA showing a control that only ever errors.
    if controller.profile.supports(CAP_AUTO_SWITCH):
        await mqtt.subscribe(f"{prefix}/auto_switch/set")
    if controller.profile.supports(CAP_EDID):
        await mqtt.subscribe(f"{prefix}/edid/set")
    log.info("command_subscriber_started", prefix=prefix)

    async for msg in mqtt.messages:
        topic_str = str(msg.topic)
        raw = msg.payload
        if isinstance(raw, bytes | bytearray):
            payload = bytes(raw).decode("utf-8", errors="replace").strip()
        elif isinstance(raw, str):
            payload = raw.strip()
        else:
            log.warning(
                "command_subscriber_bad_payload",
                topic=topic_str,
                type=type(raw).__name__,
            )
            continue

        try:
            if _POWER_SET_RE.match(topic_str):
                await controller.set_power(payload.upper())
            elif _MODE_SET_RE.match(topic_str):
                await controller.set_mode(payload)
            elif (m := _WINDOW_SET_RE.match(topic_str)) is not None:
                await controller.set_window_input(int(m.group("n")), payload)
            elif _INPUT_SOURCE_SET_RE.match(topic_str):
                await controller.set_input_source(payload)
            elif _AUDIO_SOURCE_SET_RE.match(topic_str):
                await controller.set_audio_source(payload)
            elif _AUDIO_VOLUME_SET_RE.match(topic_str):
                await controller.set_audio_volume(payload)
            elif _AUDIO_MUTED_SET_RE.match(topic_str):
                await controller.set_audio_mute(payload.upper())
            elif _PIP_POSITION_SET_RE.match(topic_str):
                await controller.set_pip_position(payload)
            elif _PIP_SIZE_SET_RE.match(topic_str):
                await controller.set_pip_size(payload)
            elif _AUTO_SWITCH_SET_RE.match(topic_str):
                await controller.set_auto_switch(payload.upper())
            elif _EDID_SET_RE.match(topic_str):
                await controller.set_edid(payload)
            else:
                log.warning("command_subscriber_unmatched_topic", topic=topic_str)
        except ControllerError as exc:
            log.warning("command_rejected", topic=topic_str, error=str(exc))
        except Exception as exc:  # pragma: no cover
            log.warning("command_failed", topic=topic_str, error=str(exc))


app = FastAPI(
    title="HDMI Multiviewer Proxy",
    description=(
        "REST + MQTT proxy for UHD-401MV multiviewer (RS-232). v0.2 adds "
        "optional MQTT publishing with Home Assistant discovery; the REST "
        "endpoints stay available for direct scripting + debug."
    ),
    version=__version__,
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(system.router, prefix="/api", tags=["System"])
app.include_router(display.router, prefix="/api", tags=["Display"])
app.include_router(audio.router, prefix="/api", tags=["Audio"])
app.include_router(output.router, prefix="/api", tags=["Output"])


@app.get("/")
async def root() -> dict:
    """Root endpoint with API info."""
    return {
        "name": "HDMI Multiviewer Proxy",
        "version": __version__,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
    )
