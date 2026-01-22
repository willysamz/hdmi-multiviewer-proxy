"""Tests for command parsing."""

import pytest

from app.commands import ResponseParser


class TestResponseParser:
    """Test response parsing functions."""

    def test_parse_power_on(self):
        """Test parsing power on response."""
        assert ResponseParser.parse_power("power on") is True
        assert ResponseParser.parse_power("Power On") is True
        assert ResponseParser.parse_power("POWER ON") is True

    def test_parse_power_off(self):
        """Test parsing power off response."""
        assert ResponseParser.parse_power("power off") is False
        assert ResponseParser.parse_power("Power Off") is False

    def test_parse_power_invalid(self):
        """Test parsing invalid power response."""
        assert ResponseParser.parse_power("invalid") is None
        assert ResponseParser.parse_power("") is None

    def test_parse_multiview_mode(self):
        """Test parsing multiview mode response."""
        assert ResponseParser.parse_multiview_mode("single screen") == "single"
        assert ResponseParser.parse_multiview_mode("PIP") == "pip"
        assert ResponseParser.parse_multiview_mode("PBP") == "pbp"
        assert ResponseParser.parse_multiview_mode("triple screen") == "triple"
        assert ResponseParser.parse_multiview_mode("quad screen") == "quad"

    def test_parse_audio_source(self):
        """Test parsing audio source response."""
        assert ResponseParser.parse_audio_source("follow window") == 0
        assert ResponseParser.parse_audio_source("HDMI 1 input audio") == 1
        assert ResponseParser.parse_audio_source("HDMI 2 input audio") == 2
        assert ResponseParser.parse_audio_source("HDMI 3 input audio") == 3
        assert ResponseParser.parse_audio_source("HDMI 4 input audio") == 4

    def test_parse_volume(self):
        """Test parsing volume response."""
        assert ResponseParser.parse_volume("output audio volume: 50") == 50
        assert ResponseParser.parse_volume("volume: 100") == 100
        assert ResponseParser.parse_volume("volume: 0") == 0
        assert ResponseParser.parse_volume("invalid") is None

    def test_parse_mute(self):
        """Test parsing mute state response."""
        assert ResponseParser.parse_mute("output audio mute: on") is True
        assert ResponseParser.parse_mute("mute: off") is False
        assert ResponseParser.parse_mute("invalid") is None

    def test_parse_resolution(self):
        """Test parsing resolution response."""
        assert ResponseParser.parse_resolution("out resolution: 3840x2160p60") == "3840x2160p60"
        assert ResponseParser.parse_resolution("resolution: 1920x1080p60") == "1920x1080p60"

    def test_parse_hdcp(self):
        """Test parsing HDCP response."""
        assert ResponseParser.parse_hdcp("output HDCP: HDCP 1.4") == "hdcp_1_4"
        assert ResponseParser.parse_hdcp("HDCP 2.2") == "hdcp_2_2"
        assert ResponseParser.parse_hdcp("HDCP OFF") == "off"

    def test_parse_pip_position(self):
        """Test parsing PIP position response."""
        assert ResponseParser.parse_pip_position("PIP on left top") == "left_top"
        assert ResponseParser.parse_pip_position("left bottom") == "left_bottom"
        assert ResponseParser.parse_pip_position("right top") == "right_top"
        assert ResponseParser.parse_pip_position("right bottom") == "right_bottom"

    def test_parse_pip_size(self):
        """Test parsing PIP size response."""
        assert ResponseParser.parse_pip_size("PIP size: small") == "small"
        assert ResponseParser.parse_pip_size("middle") == "middle"
        assert ResponseParser.parse_pip_size("large") == "large"

    def test_parse_window_input(self):
        """Test parsing window input response."""
        assert ResponseParser.parse_window_input("window 1 select HDMI 1") == 1
        assert ResponseParser.parse_window_input("HDMI 2") == 2
        assert ResponseParser.parse_window_input("HDMI 3") == 3
        assert ResponseParser.parse_window_input("HDMI 4") == 4

    def test_parse_aspect(self):
        """Test parsing aspect ratio response."""
        assert ResponseParser.parse_aspect("full screen") == "full_screen"
        assert ResponseParser.parse_aspect("16:9") == "16_9"
