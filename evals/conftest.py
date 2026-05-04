"""Pytest fixtures for evaluation suite."""
import sys
from pathlib import Path

import pytest

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed, use shell env

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def rag_engine():
    """Initialize RAG engine once for all tests."""
    from app.RAG import _RAGEngine
    engine = _RAGEngine()
    engine._init()
    return engine


@pytest.fixture(scope="session")
def crm_tool():
    """Initialize CRM tool for tests."""
    from app.tools import CRMTool
    return CRMTool()


@pytest.fixture(scope="session")
def appointment_tool():
    """Initialize Appointment tool for tests."""
    from app.tools import AppointmentTool
    return AppointmentTool()


@pytest.fixture(scope="session")
def weather_tool():
    """Initialize Weather tool for tests."""
    from app.tools import WeatherTool
    return WeatherTool()


@pytest.fixture(scope="session")
def cost_tool():
    """Initialize DentalCost tool for tests."""
    from app.tools import DentalCostTool
    return DentalCostTool()
