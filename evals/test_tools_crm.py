"""
Unit tests for CRM Tool.

Tests CRUD operations:
- Create patient record
- Read patient record
- Update patient record
- Verify data persistence

Run: pytest evals/test_tools_crm.py -v
"""
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools import CRMTool


class TestCRMTool:
    """Test CRM tool CRUD operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Initialize CRM tool and create unique session ID for each test."""
        self.crm = CRMTool()
        self.test_session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        yield
        # Cleanup: delete test patient after test
        self._cleanup_patient(self.test_session_id)

    def _cleanup_patient(self, session_id: str):
        """Remove test patient from database."""
        import sqlite3
        db_path = os.getenv("DENTABOT_DB_PATH", "dentabot.db")
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("DELETE FROM patients WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════════════════
    # CREATE Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_create_new_patient(self):
        """Test creating a new patient record."""
        result = self.crm.upsert_patient(
            session_id=self.test_session_id,
            name="John Doe",
            contact="0301-1234567",
            last_service="checkup",
            notes="Test patient"
        )

        assert result is not None
        assert result["session_id"] == self.test_session_id
        assert result["name"] == "John Doe"
        assert result["contact"] == "0301-1234567"
        assert result["last_service"] == "checkup"
        assert result["visit_count"] == 1

    def test_create_patient_with_minimal_data(self):
        """Test creating patient with only session_id."""
        result = self.crm.upsert_patient(session_id=self.test_session_id)

        assert result is not None
        assert result["session_id"] == self.test_session_id
        assert result["visit_count"] == 1

    # ════════════════════════════════════════════════════════════════════════
    # READ Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_read_existing_patient(self):
        """Test reading an existing patient record."""
        # First create
        self.crm.upsert_patient(
            session_id=self.test_session_id,
            name="Jane Smith"
        )

        # Then read
        result = self.crm.get_patient(self.test_session_id)

        assert result is not None
        assert result["name"] == "Jane Smith"

    def test_read_nonexistent_patient(self):
        """Test reading a patient that doesn't exist."""
        result = self.crm.get_patient("nonexistent_session_xyz123")

        assert result is None

    # ════════════════════════════════════════════════════════════════════════
    # UPDATE Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_update_patient_name(self):
        """Test updating patient name."""
        # Create
        self.crm.upsert_patient(session_id=self.test_session_id, name="Old Name")

        # Update
        result = self.crm.upsert_patient(session_id=self.test_session_id, name="New Name")

        assert result["name"] == "New Name"
        assert result["visit_count"] == 2  # Incremented on update

    def test_update_patient_contact(self):
        """Test updating patient contact."""
        self.crm.upsert_patient(session_id=self.test_session_id, contact="0300-0000000")
        result = self.crm.upsert_patient(session_id=self.test_session_id, contact="0321-9999999")

        assert result["contact"] == "0321-9999999"

    def test_update_increments_visit_count(self):
        """Test that each update increments visit count."""
        self.crm.upsert_patient(session_id=self.test_session_id, name="Test")
        self.crm.upsert_patient(session_id=self.test_session_id, name="Test")
        result = self.crm.upsert_patient(session_id=self.test_session_id, name="Test")

        assert result["visit_count"] == 3

    def test_partial_update_preserves_existing_data(self):
        """Test that partial update doesn't overwrite other fields."""
        # Create with full data
        self.crm.upsert_patient(
            session_id=self.test_session_id,
            name="Full Name",
            contact="0300-1111111",
            last_service="cleaning"
        )

        # Update only name
        result = self.crm.upsert_patient(
            session_id=self.test_session_id,
            name="Updated Name"
        )

        assert result["name"] == "Updated Name"
        assert result["contact"] == "0300-1111111"  # Preserved
        assert result["last_service"] == "cleaning"  # Preserved

    # ════════════════════════════════════════════════════════════════════════
    # Persistence Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_data_persists_across_instances(self):
        """Test that data persists when creating new CRM instance."""
        # Create patient with first instance
        self.crm.upsert_patient(session_id=self.test_session_id, name="Persistent User")

        # Create new CRM instance
        new_crm = CRMTool()

        # Read with new instance
        result = new_crm.get_patient(self.test_session_id)

        assert result is not None
        assert result["name"] == "Persistent User"

    # ════════════════════════════════════════════════════════════════════════
    # Edge Cases
    # ════════════════════════════════════════════════════════════════════════

    def test_special_characters_in_name(self):
        """Test handling special characters in name."""
        result = self.crm.upsert_patient(
            session_id=self.test_session_id,
            name="O'Brien-Smith"
        )

        assert result["name"] == "O'Brien-Smith"

    def test_unicode_in_notes(self):
        """Test handling unicode characters."""
        result = self.crm.upsert_patient(
            session_id=self.test_session_id,
            notes="Patient speaks اردو"
        )

        assert "اردو" in result["notes"]

    def test_empty_string_values(self):
        """Test handling empty strings."""
        result = self.crm.upsert_patient(
            session_id=self.test_session_id,
            name="",
            contact=""
        )

        assert result is not None


# ════════════════════════════════════════════════════════════════════════════
# Standalone Runner
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
