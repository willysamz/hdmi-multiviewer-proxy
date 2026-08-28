"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    # --- Serial port settings ---
    serial_port: str = "/dev/ttyUSB0"
    serial_baud_rate: int = 115200
    serial_timeout: float = 2.0
    serial_heartbeat_interval: int = 30
    serial_reconnect_backoff_max: int = 30

    # --- MQTT poll cadence (v0.2+) ---
    # Used by the MQTT publisher to read state from the multiviewer
    # and publish deltas. Ignored when mqtt_enabled is False.
    poll_interval: float = 10.0

    # --- MQTT broker (v0.2+) ---
    # When mqtt_enabled is False, the proxy behaves like v0.1.x — REST
    # only, HA polls the proxy. When True, the poller publishes state +
    # HA discovery; the controller subscribes to per-entity command topics.
    mqtt_enabled: bool = False
    mqtt_host: str = "mqtt"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_client_id: str = "hdmi-multiviewer-proxy"
    mqtt_topic_prefix: str = "multiviewer"
    mqtt_keepalive: int = 60
    mqtt_qos: int = 0  # 0|1|2

    # --- Home Assistant MQTT discovery (v0.2+) ---
    ha_discovery_enabled: bool = True
    ha_discovery_prefix: str = "homeassistant"
    ha_device_name: str = "HDMI Multiviewer"
    # Stable device id used in unique_id + HA device card. Default keeps
    # entity_ids predictable across reinstalls.
    ha_device_id: str = "hdmi_multiviewer"
    # HA device card `model`. Default matches the basement unit; the garage
    # instance overrides this to report its own hardware model.
    ha_device_model: str = "UHD-401MV 4-port HDMI Multiviewer"

    # --- Device profile (v0.4+) ---
    # Which multiviewer model this instance drives. The two supported models
    # are NOT command-compatible -- notably the UHD takes `power z!` while the
    # HDS takes `s power z!`, and the HDS has no volume/HDCP/VKA/ITC commands
    # at all. `r type!` returns the same string on both, so this cannot be
    # auto-detected and must be set per instance.
    #
    # BREAKING in 0.4.0: an HDS instance MUST set device_profile=hds401mv.
    # Leaving the default sends it UHD-form power commands, which it ignores.
    device_profile: str = "uhd401mv"

    # --- Server settings ---
    server_host: str = "0.0.0.0"  # noqa: S104
    server_port: int = 8080

    # --- Logging ---
    log_level: str = "INFO"
    log_json: bool = True


settings = Settings()
