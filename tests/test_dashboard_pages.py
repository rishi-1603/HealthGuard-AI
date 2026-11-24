"""
Unit tests for HealthGuard 360 multi-page Streamlit dashboard extensions:
  - app/dashboard/pages/07_Data_Trust_Console.py
  - app/dashboard/pages/08_AI_Data_Copilot.py
"""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_data_trust_console_page_renders():
    """Verifies that 07_Data_Trust_Console.py executes without exception."""
    page_path = REPO_ROOT / "app" / "dashboard" / "pages" / "07_Data_Trust_Console.py"
    assert page_path.exists(), "07_Data_Trust_Console.py must exist"

    at = AppTest.from_file(str(page_path), default_timeout=30)
    at.run()
    assert not at.exception, f"Raised exception: {at.exception}"
    assert len(at.error) == 0, [e.value for e in at.error]


def test_ai_data_copilot_page_renders():
    """Verifies that 08_AI_Data_Copilot.py executes and displays tabs without exception."""
    page_path = REPO_ROOT / "app" / "dashboard" / "pages" / "08_AI_Data_Copilot.py"
    assert page_path.exists(), "08_AI_Data_Copilot.py must exist"

    at = AppTest.from_file(str(page_path), default_timeout=30)
    at.run()
    assert not at.exception, f"Raised exception: {at.exception}"
    assert len(at.error) == 0, [e.value for e in at.error]
    assert len(at.tabs) == 2
    assert "Interactive Clinical Copilot" in at.tabs[0].label
    assert "Governance Benchmark" in at.tabs[1].label
