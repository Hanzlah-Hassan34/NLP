"""
Unit tests for Weather Tool.

Tests:
- Successful weather fetch
- Response format validation
- Error handling

Run: pytest evals/test_tools_weather.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch, Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools import WeatherTool


class TestWeatherTool:
    """Test Weather tool operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Initialize weather tool."""
        self.weather = WeatherTool()

    # ════════════════════════════════════════════════════════════════════════
    # Live API Tests (may fail without internet)
    # ════════════════════════════════════════════════════════════════════════

    @pytest.mark.network
    def test_get_weather_lahore_live(self):
        """Test getting weather for Lahore (live API call)."""
        result = self.weather.get_weather("Lahore")

        # Should either succeed or have an error
        if "error" not in result:
            assert result["city"] == "Lahore"
            assert "temperature_c" in result
            assert "description" in result

    @pytest.mark.network
    def test_get_weather_default_city(self):
        """Test default city is Lahore."""
        result = self.weather.get_weather()

        if "error" not in result:
            assert result["city"] == "Lahore"

    # ════════════════════════════════════════════════════════════════════════
    # Mocked API Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_get_weather_success_mocked(self):
        """Test successful weather response with mocked API."""
        mock_response = {
            "current_condition": [{
                "temp_C": "32",
                "FeelsLikeC": "35",
                "weatherDesc": [{"value": "Sunny"}],
                "humidity": "45",
                "windspeedKmph": "12"
            }]
        }

        with patch("app.tools.requests.get") as mock_get:
            mock_get.return_value = Mock(
                status_code=200,
                json=lambda: mock_response
            )

            result = self.weather.get_weather("Lahore")

            assert result["city"] == "Lahore"
            assert result["temperature_c"] == "32"
            assert result["feels_like_c"] == "35"
            assert result["description"] == "Sunny"
            assert result["humidity"] == "45"
            assert result["wind_kmph"] == "12"

    def test_get_weather_api_error(self):
        """Test handling API error."""
        with patch("app.tools.requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=500)

            result = self.weather.get_weather("Lahore")

            assert "error" in result
            assert result["city"] == "Lahore"

    def test_get_weather_network_error(self):
        """Test handling network error."""
        with patch("app.tools.requests.get") as mock_get:
            mock_get.side_effect = Exception("Connection timeout")

            result = self.weather.get_weather("Lahore")

            assert "error" in result
            assert "timeout" in result["error"].lower() or "connection" in result["error"].lower()

    def test_get_weather_invalid_json(self):
        """Test handling invalid JSON response."""
        with patch("app.tools.requests.get") as mock_get:
            mock_get.return_value = Mock(
                status_code=200,
                json=lambda: {"unexpected": "format"}
            )

            result = self.weather.get_weather("Lahore")

            # Should handle gracefully with error
            assert "error" in result or "city" in result

    # ════════════════════════════════════════════════════════════════════════
    # Response Format Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_response_format_on_success(self):
        """Test that successful response has all required fields."""
        mock_response = {
            "current_condition": [{
                "temp_C": "25",
                "FeelsLikeC": "27",
                "weatherDesc": [{"value": "Partly cloudy"}],
                "humidity": "60",
                "windspeedKmph": "8"
            }]
        }

        with patch("app.tools.requests.get") as mock_get:
            mock_get.return_value = Mock(
                status_code=200,
                json=lambda: mock_response
            )

            result = self.weather.get_weather("Karachi")

            required_fields = [
                "city", "temperature_c", "feels_like_c",
                "description", "humidity", "wind_kmph"
            ]
            for field in required_fields:
                assert field in result, f"Missing field: {field}"

    def test_response_format_on_error(self):
        """Test that error response has required fields."""
        with patch("app.tools.requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=503)

            result = self.weather.get_weather("TestCity")

            assert "error" in result
            assert "city" in result

    # ════════════════════════════════════════════════════════════════════════
    # Edge Cases
    # ════════════════════════════════════════════════════════════════════════

    def test_city_with_spaces(self):
        """Test city name with spaces."""
        mock_response = {
            "current_condition": [{
                "temp_C": "20",
                "FeelsLikeC": "22",
                "weatherDesc": [{"value": "Clear"}],
                "humidity": "50",
                "windspeedKmph": "5"
            }]
        }

        with patch("app.tools.requests.get") as mock_get:
            mock_get.return_value = Mock(
                status_code=200,
                json=lambda: mock_response
            )

            result = self.weather.get_weather("New York")

            assert result["city"] == "New York"


# ════════════════════════════════════════════════════════════════════════════
# Standalone Runner
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not network"])
