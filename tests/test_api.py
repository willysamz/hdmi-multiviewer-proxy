"""Tests for API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# Mock the serial handler before importing the app
@pytest.fixture
def mock_serial_handler():
    """Create a mock serial handler."""
    handler = MagicMock()
    handler.state = MagicMock()
    handler.state.value = "on"
    handler.is_connected = True
    handler.is_initialized = True
    handler.last_heartbeat = None
    handler.port = "/dev/ttyUSB0"
    handler.send_command = AsyncMock(return_value=(True, "power on", None))
    return handler


@pytest.fixture
def client(mock_serial_handler):
    """Create a test client with mocked dependencies."""
    from app.dependencies import set_serial_handler, set_startup_time
    from datetime import datetime, timezone

    set_startup_time(datetime.now(timezone.utc))
    set_serial_handler(mock_serial_handler)

    from app.main import app
    return TestClient(app)


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_liveness_probe(self, client):
        """Test liveness probe returns 200."""
        response = client.get("/healthz/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_readiness_probe(self, client):
        """Test readiness probe returns 200 when ready."""
        response = client.get("/healthz/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "HDMI Multiviewer Proxy"
        assert "version" in data
        assert data["docs"] == "/docs"


class TestStatusEndpoint:
    """Test status endpoint."""

    def test_get_status(self, client, mock_serial_handler):
        """Test getting device status."""
        mock_serial_handler.send_command = AsyncMock(
            side_effect=[
                (True, "power on", None),
                (True, "4x1 HDMI Multiviewer", None),
                (True, "MCU FW version 1.0.0", None),
            ]
        )

        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connection"] == "on"
        assert data["port"] == "/dev/ttyUSB0"


class TestAudioEndpoints:
    """Test audio endpoints."""

    def test_get_audio(self, client, mock_serial_handler):
        """Test getting audio settings."""
        mock_serial_handler.send_command = AsyncMock(
            side_effect=[
                (True, "output audio: HDMI 1 input audio", None),
                (True, "output audio volume: 50", None),
                (True, "output audio mute: off", None),
            ]
        )

        response = client.get("/api/audio")
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == 1
        assert data["volume"] == 50
        assert data["muted"] is False

    def test_set_audio_source(self, client, mock_serial_handler):
        """Test setting audio source."""
        mock_serial_handler.send_command = AsyncMock(
            side_effect=[
                (True, "output audio: HDMI 2 input audio", None),
                (True, "output audio: HDMI 2 input audio", None),
                (True, "output audio volume: 50", None),
                (True, "output audio mute: off", None),
            ]
        )

        response = client.post("/api/audio/source", json={"source": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == 2
