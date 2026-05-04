"""
Unit tests for DentalCost Tool.

Tests:
- Known procedure costs
- Unknown procedure handling
- Cost range validation
- Various input formats

Run: pytest evals/test_tools_cost.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools import DentalCostTool, PROCEDURE_COSTS


class TestDentalCostTool:
    """Test DentalCost tool operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Initialize cost tool."""
        self.cost = DentalCostTool()

    # ════════════════════════════════════════════════════════════════════════
    # Known Procedures Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_checkup_cost(self):
        """Test checkup cost retrieval."""
        result = self.cost.get_cost("checkup")

        assert "min_cost_pkr" in result
        assert "max_cost_pkr" in result
        assert result["min_cost_pkr"] == 500
        assert result["max_cost_pkr"] == 1000

    def test_routine_checkup_cost(self):
        """Test routine check-up cost retrieval."""
        result = self.cost.get_cost("routine check-up")

        assert result["min_cost_pkr"] == 500
        assert result["max_cost_pkr"] == 1000

    def test_cleaning_cost(self):
        """Test teeth cleaning cost."""
        result = self.cost.get_cost("cleaning")

        assert result["min_cost_pkr"] == 1500
        assert result["max_cost_pkr"] == 3000

    def test_root_canal_cost(self):
        """Test root canal cost."""
        result = self.cost.get_cost("root canal")

        assert result["min_cost_pkr"] == 8000
        assert result["max_cost_pkr"] == 15000

    def test_braces_cost(self):
        """Test braces cost."""
        result = self.cost.get_cost("braces")

        assert result["min_cost_pkr"] == 40000
        assert result["max_cost_pkr"] == 120000

    def test_invisalign_cost(self):
        """Test Invisalign cost."""
        result = self.cost.get_cost("invisalign")

        assert result["min_cost_pkr"] == 80000
        assert result["max_cost_pkr"] == 200000

    def test_whitening_cost(self):
        """Test teeth whitening cost."""
        result = self.cost.get_cost("whitening")

        assert result["min_cost_pkr"] == 5000
        assert result["max_cost_pkr"] == 12000

    def test_extraction_cost(self):
        """Test tooth extraction cost."""
        result = self.cost.get_cost("extraction")

        assert result["min_cost_pkr"] == 1500
        assert result["max_cost_pkr"] == 4000

    def test_filling_cost(self):
        """Test filling cost."""
        result = self.cost.get_cost("filling")

        assert result["min_cost_pkr"] == 2000
        assert result["max_cost_pkr"] == 5000

    def test_xray_cost(self):
        """Test dental X-ray cost."""
        result = self.cost.get_cost("x-ray")

        assert result["min_cost_pkr"] == 800
        assert result["max_cost_pkr"] == 1500

    def test_crown_cost(self):
        """Test dental crown cost."""
        result = self.cost.get_cost("crown")

        assert result["min_cost_pkr"] == 10000
        assert result["max_cost_pkr"] == 25000

    def test_veneer_cost(self):
        """Test veneer cost."""
        result = self.cost.get_cost("veneer")

        assert result["min_cost_pkr"] == 15000
        assert result["max_cost_pkr"] == 35000

    # ════════════════════════════════════════════════════════════════════════
    # Unknown Procedure Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_unknown_procedure(self):
        """Test unknown procedure handling."""
        result = self.cost.get_cost("xyz_unknown_procedure")

        assert "message" in result
        assert "unavailable" in result["message"].lower()
        assert "note" in result

    def test_unknown_procedure_has_contact_info(self):
        """Test that unknown procedure response includes contact info."""
        result = self.cost.get_cost("some random procedure")

        assert "042-35001234" in result.get("note", "")

    # ════════════════════════════════════════════════════════════════════════
    # Input Format Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_case_insensitive(self):
        """Test case insensitivity."""
        result_lower = self.cost.get_cost("checkup")
        result_upper = self.cost.get_cost("CHECKUP")
        result_mixed = self.cost.get_cost("ChEcKuP")

        assert result_lower["min_cost_pkr"] == result_upper["min_cost_pkr"]
        assert result_lower["min_cost_pkr"] == result_mixed["min_cost_pkr"]

    def test_whitespace_handling(self):
        """Test whitespace is trimmed."""
        result = self.cost.get_cost("  cleaning  ")

        assert "min_cost_pkr" in result
        assert result["min_cost_pkr"] == 1500

    def test_partial_match(self):
        """Test partial matching works."""
        result = self.cost.get_cost("I need a cleaning please")

        assert "min_cost_pkr" in result
        assert result["min_cost_pkr"] == 1500

    def test_teeth_cleaning_variant(self):
        """Test 'teeth cleaning' vs 'cleaning'."""
        result = self.cost.get_cost("teeth cleaning")

        assert "min_cost_pkr" in result

    # ════════════════════════════════════════════════════════════════════════
    # Response Format Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_success_response_format(self):
        """Test successful response has all fields."""
        result = self.cost.get_cost("checkup")

        assert "procedure" in result
        assert "min_cost_pkr" in result
        assert "max_cost_pkr" in result
        assert "note" in result

    def test_success_response_has_note(self):
        """Test that note mentions insurance."""
        result = self.cost.get_cost("cleaning")

        assert "insurance" in result["note"].lower()

    def test_procedure_name_is_titlecased(self):
        """Test procedure name is title-cased in response."""
        result = self.cost.get_cost("root canal")

        assert result["procedure"] == "Root Canal"

    # ════════════════════════════════════════════════════════════════════════
    # Coverage Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_all_procedures_have_valid_costs(self):
        """Test all defined procedures return valid costs."""
        for procedure in PROCEDURE_COSTS.keys():
            result = self.cost.get_cost(procedure)

            assert "min_cost_pkr" in result, f"No min cost for {procedure}"
            assert "max_cost_pkr" in result, f"No max cost for {procedure}"
            assert result["min_cost_pkr"] <= result["max_cost_pkr"], \
                f"Min > Max for {procedure}"

    def test_costs_are_positive(self):
        """Test all costs are positive numbers."""
        for procedure in PROCEDURE_COSTS.keys():
            result = self.cost.get_cost(procedure)

            assert result["min_cost_pkr"] > 0
            assert result["max_cost_pkr"] > 0


# ════════════════════════════════════════════════════════════════════════════
# Standalone Runner
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
