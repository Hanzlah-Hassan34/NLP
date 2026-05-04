"""
Unit tests for Appointment Tool.

Tests:
- Get available slots
- Book appointment
- Get patient appointments
- Cancel appointment
- Slot collision handling

Run: pytest evals/test_tools_appointment.py -v
"""
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools import AppointmentTool, AVAILABLE_TIMES, DOCTOR_SCHEDULE


class TestAppointmentTool:
    """Test Appointment tool operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Initialize appointment tool and test data."""
        self.appointment = AppointmentTool()
        self.test_session_id = f"test_appt_{uuid.uuid4().hex[:8]}"
        self.test_patient_name = f"Test Patient {uuid.uuid4().hex[:4]}"
        self.booked_appointments = []
        yield
        # Cleanup
        self._cleanup_appointments()

    def _cleanup_appointments(self):
        """Remove test appointments from database."""
        import sqlite3
        db_path = os.getenv("DENTABOT_DB_PATH", "dentabot.db")
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "DELETE FROM appointments WHERE session_id = ?",
                (self.test_session_id,)
            )
            conn.execute(
                "DELETE FROM appointments WHERE patient_name LIKE ?",
                (f"%{self.test_patient_name}%",)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _get_future_date(self, days_ahead: int = 1) -> str:
        """Get a future date string in the format used by the system."""
        future = datetime.now() + timedelta(days=days_ahead)
        # Skip Sundays
        while future.strftime("%A") == "Sunday":
            future += timedelta(days=1)
        return future.strftime("%A, %d %B %Y")

    # ════════════════════════════════════════════════════════════════════════
    # Get Available Slots Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_get_available_slots_returns_slots(self):
        """Test that available slots are returned."""
        slots = self.appointment.get_available_slots(limit=5)

        assert isinstance(slots, list)
        assert len(slots) > 0
        assert len(slots) <= 5

    def test_available_slots_have_required_fields(self):
        """Test that each slot has required fields."""
        slots = self.appointment.get_available_slots(limit=3)

        for slot in slots:
            assert "date" in slot
            assert "time" in slot
            assert "doctors" in slot
            assert isinstance(slot["doctors"], list)

    def test_available_slots_are_future_dates(self):
        """Test that slots are in the future."""
        slots = self.appointment.get_available_slots(limit=5)
        today = datetime.now().date()

        for slot in slots:
            # Parse date from slot
            date_str = slot["date"]
            # Extract just the date part
            slot_date = datetime.strptime(date_str, "%A, %d %B %Y").date()
            assert slot_date > today, f"Slot date {slot_date} is not in the future"

    def test_available_slots_exclude_sundays(self):
        """Test that no slots are on Sunday."""
        slots = self.appointment.get_available_slots(limit=20)

        for slot in slots:
            assert not slot["date"].startswith("Sunday")

    def test_available_times_are_valid(self):
        """Test that slot times are from AVAILABLE_TIMES."""
        slots = self.appointment.get_available_slots(limit=10)

        for slot in slots:
            assert slot["time"] in AVAILABLE_TIMES

    # ════════════════════════════════════════════════════════════════════════
    # Book Appointment Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_book_appointment_success(self):
        """Test successful appointment booking."""
        date = self._get_future_date(days_ahead=3)
        time = "10:00 AM"

        result = self.appointment.book_appointment(
            session_id=self.test_session_id,
            patient_name=self.test_patient_name,
            contact="0300-1234567",
            service="checkup",
            date=date,
            time=time
        )

        assert result["success"] is True
        assert "appointment_id" in result
        assert result["patient_name"] == self.test_patient_name
        assert result["service"] == "checkup"

    def test_book_appointment_returns_doctor(self):
        """Test that booking assigns a doctor."""
        date = self._get_future_date(days_ahead=4)
        time = "11:00 AM"

        result = self.appointment.book_appointment(
            session_id=self.test_session_id,
            patient_name=self.test_patient_name,
            contact="0300-1234567",
            service="cleaning",
            date=date,
            time=time
        )

        assert "doctor" in result
        assert result["doctor"] is not None

    def test_book_appointment_slot_collision(self):
        """Test that double-booking same slot fails."""
        date = self._get_future_date(days_ahead=5)
        time = "2:00 PM"

        # First booking
        result1 = self.appointment.book_appointment(
            session_id=self.test_session_id,
            patient_name=self.test_patient_name,
            contact="0300-1111111",
            service="checkup",
            date=date,
            time=time
        )

        assert result1["success"] is True

        # Second booking same slot
        result2 = self.appointment.book_appointment(
            session_id=f"{self.test_session_id}_2",
            patient_name="Another Patient",
            contact="0300-2222222",
            service="cleaning",
            date=date,
            time=time
        )

        assert result2["success"] is False
        assert "already taken" in result2["message"].lower()

    def test_book_appointment_time_normalization(self):
        """Test that time is normalized correctly."""
        date = self._get_future_date(days_ahead=6)

        # Book with different time format
        result = self.appointment.book_appointment(
            session_id=self.test_session_id,
            patient_name=self.test_patient_name,
            contact="0300-1234567",
            service="checkup",
            date=date,
            time="3pm"  # Without colon and space
        )

        assert result["success"] is True
        assert result["time"] == "3:00 PM"

    # ════════════════════════════════════════════════════════════════════════
    # Get Patient Appointments Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_get_patient_appointments_returns_bookings(self):
        """Test getting appointments for a patient."""
        date = self._get_future_date(days_ahead=7)

        # Book an appointment first
        self.appointment.book_appointment(
            session_id=self.test_session_id,
            patient_name=self.test_patient_name,
            contact="0300-1234567",
            service="checkup",
            date=date,
            time="9:00 AM"
        )

        # Get appointments
        appointments = self.appointment.get_patient_appointments(self.test_patient_name)

        assert isinstance(appointments, list)
        assert len(appointments) >= 1

    def test_get_patient_appointments_empty_for_new_patient(self):
        """Test that new patient has no appointments."""
        appointments = self.appointment.get_patient_appointments("NonexistentPatient12345")

        assert isinstance(appointments, list)
        assert len(appointments) == 0

    def test_get_patient_appointments_partial_name_match(self):
        """Test partial name matching."""
        date = self._get_future_date(days_ahead=8)
        full_name = f"Muhammad {self.test_patient_name}"

        self.appointment.book_appointment(
            session_id=self.test_session_id,
            patient_name=full_name,
            contact="0300-1234567",
            service="cleaning",
            date=date,
            time="4:00 PM"
        )

        # Search with partial name
        appointments = self.appointment.get_patient_appointments(self.test_patient_name)

        assert len(appointments) >= 1

    # ════════════════════════════════════════════════════════════════════════
    # Cancel Appointment Tests
    # ════════════════════════════════════════════════════════════════════════

    def test_cancel_appointment_success(self):
        """Test successful appointment cancellation."""
        date = self._get_future_date(days_ahead=9)

        # Book first
        booking = self.appointment.book_appointment(
            session_id=self.test_session_id,
            patient_name=self.test_patient_name,
            contact="0300-1234567",
            service="checkup",
            date=date,
            time="5:00 PM"
        )

        appt_id = booking["appointment_id"]

        # Cancel
        result = self.appointment.cancel_appointment(appt_id)

        assert result["success"] is True
        assert str(appt_id) in result["message"]

    def test_cancelled_appointment_not_in_active_list(self):
        """Test that cancelled appointments don't appear in patient list."""
        date = self._get_future_date(days_ahead=10)

        # Book
        booking = self.appointment.book_appointment(
            session_id=self.test_session_id,
            patient_name=self.test_patient_name,
            contact="0300-1234567",
            service="checkup",
            date=date,
            time="6:00 PM"
        )

        # Cancel
        self.appointment.cancel_appointment(booking["appointment_id"])

        # Check appointments
        appointments = self.appointment.get_patient_appointments(self.test_patient_name)

        # Cancelled appointment should not appear (status != 'confirmed')
        cancelled_found = any(
            a["id"] == booking["appointment_id"] for a in appointments
        )
        assert not cancelled_found

    def test_cancelled_slot_becomes_available(self):
        """Test that cancelled slot can be rebooked."""
        import random
        # Use random time to avoid collision with other test runs
        random_hour = random.choice([9, 11, 14, 15, 16])
        date = self._get_future_date(days_ahead=15)
        time = f"{random_hour}:00 AM" if random_hour < 12 else f"{random_hour-12}:00 PM"

        # Book
        booking1 = self.appointment.book_appointment(
            session_id=self.test_session_id,
            patient_name=self.test_patient_name,
            contact="0300-1234567",
            service="checkup",
            date=date,
            time=time
        )
        
        # Skip test if slot already taken
        if not booking1.get("success"):
            pytest.skip("Slot already taken from previous run")

        # Cancel
        self.appointment.cancel_appointment(booking1["appointment_id"])

        # Rebook same slot
        booking2 = self.appointment.book_appointment(
            session_id=f"{self.test_session_id}_new",
            patient_name="New Patient",
            contact="0300-9999999",
            service="cleaning",
            date=date,
            time=time
        )

        assert booking2["success"] is True


# ════════════════════════════════════════════════════════════════════════════
# Standalone Runner
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
