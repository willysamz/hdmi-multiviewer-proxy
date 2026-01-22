"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    # Serial port settings
    serial_port: str = "/dev/ttyUSB0"
    serial_baud_rate: int = 115200
    serial_timeout: float = 2.0
    serial_heartbeat_interval: int = 30
    serial_reconnect_backoff_max: int = 30

    # Server settings
    server_host: str = "0.0.0.0"
    server_port: int = 8080

    # Logging
    log_level: str = "INFO"
    log_json: bool = True


settings = Settings()
