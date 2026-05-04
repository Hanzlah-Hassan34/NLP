"""
tools.py – Four callable tools for DentaBot Assignment 4.

  1. CRMTool          – SQLite patient records (mandatory)
  2. AppointmentTool  – SQLite appointment booking/lookup
  3. WeatherTool      – Current weather via wttr.in (no API key)
  4. DentalCostTool   – Local PKR cost estimates for procedures

All methods are synchronous; they are called from inside asyncio.to_thread
in engine.py so blocking I/O is fine here.
"""

from __future__ import annotations

import os
import sqlite3
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

# ── Database setup ─────────────────────────────────────────────────────────────

DB_PATH = os.getenv("DENTABOT_DB_PATH", "dentabot.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            session_id   TEXT PRIMARY KEY,
            name         TEXT,
            contact      TEXT,
            last_service TEXT,
            visit_count  INTEGER DEFAULT 0,
            notes        TEXT,
            created_at   TEXT,
            updated_at   TEXT
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   TEXT,
            patient_name TEXT,
            contact      TEXT,
            service      TEXT,
            date         TEXT,
            time         TEXT,
            doctor       TEXT,
            status       TEXT DEFAULT 'confirmed',
            created_at   TEXT
        );
    """)
    conn.commit()
    conn.close()


_init_db()


def _normalize_time(value: str) -> str:
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s?(am|pm)\b", value.strip(), re.IGNORECASE)
    if not match:
        return value.strip()

    hour = int(match.group(1))
    minute = int(match.group(2) or "00")
    meridiem = match.group(3).upper()
    if hour < 1 or hour > 12 or minute < 0 or minute > 59:
        return value.strip()
    return f"{hour}:{minute:02d} {meridiem}"

# ── Doctor schedule & times ────────────────────────────────────────────────────

DOCTOR_SCHEDULE: Dict[str, List[str]] = {
    "Monday":    ["Dr. Rehan", "Dr. Farhan"],
    "Tuesday":   ["Dr. Nadia"],
    "Wednesday": ["Dr. Rehan"],
    "Thursday":  ["Dr. Nadia", "Dr. Farhan"],
    "Friday":    ["Dr. Rehan"],
    "Saturday":  ["Dr. Nadia", "Dr. Farhan"],
}

AVAILABLE_TIMES = [
    "9:00 AM", "10:00 AM", "11:00 AM", "12:00 PM",
    "2:00 PM", "3:00 PM", "4:00 PM", "5:00 PM", "6:00 PM",
]

# ── Procedure cost table (PKR) ─────────────────────────────────────────────────

PROCEDURE_COSTS: Dict[str, Dict[str, int]] = {
    "routine check-up": {"min": 500,   "max": 1000},
    "checkup":          {"min": 500,   "max": 1000},
    "teeth cleaning":   {"min": 1500,  "max": 3000},
    "cleaning":         {"min": 1500,  "max": 3000},
    "tooth filling":    {"min": 2000,  "max": 5000},
    "filling":          {"min": 2000,  "max": 5000},
    "root canal":       {"min": 8000,  "max": 15000},
    "tooth extraction": {"min": 1500,  "max": 4000},
    "extraction":       {"min": 1500,  "max": 4000},
    "braces":           {"min": 40000, "max": 120000},
    "invisalign":       {"min": 80000, "max": 200000},
    "teeth whitening":  {"min": 5000,  "max": 12000},
    "whitening":        {"min": 5000,  "max": 12000},
    "dental x-ray":     {"min": 800,   "max": 1500},
    "x-ray":            {"min": 800,   "max": 1500},
    "consultation":     {"min": 500,   "max": 1500},
    "crown":            {"min": 10000, "max": 25000},
    "veneer":           {"min": 15000, "max": 35000},
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. CRM Tool
# ══════════════════════════════════════════════════════════════════════════════

class CRMTool:
    """
    Stores and retrieves patient profile data keyed by session_id.

    Schema:
      get_patient(session_id) → dict | None
      upsert_patient(session_id, name, contact, last_service, notes) → dict
    """

    name = "crm"
    description = (
        "Retrieve or update a patient's profile (name, contact, visit history) "
        "using their session ID. Call on greeting to personalise returning patients, "
        "and after collecting name/contact to persist the data."
    )

    def get_patient(self, session_id: str) -> Optional[Dict[str, Any]]:
        print(f"[TOOL][CRM][INPUT] get_patient session_id={session_id}")
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM patients WHERE session_id = ?", (session_id,)
        ).fetchone()
        conn.close()
        result = dict(row) if row else None
        print(f"[TOOL][CRM][OUTPUT] get_patient result={result}")
        return result

    def upsert_patient(
        self,
        session_id: str,
        name: Optional[str] = None,
        contact: Optional[str] = None,
        last_service: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        print(
            "[TOOL][CRM][INPUT] upsert_patient "
            f"session_id={session_id}, name={name}, contact={contact}, "
            f"last_service={last_service}, notes={notes}"
        )
        conn = _get_conn()
        now = datetime.utcnow().isoformat()
        existing = conn.execute(
            "SELECT session_id FROM patients WHERE session_id = ?", (session_id,)
        ).fetchone()

        if existing:
            updates, params = [], []
            for col, val in [
                ("name", name),
                ("contact", contact),
                ("last_service", last_service),
                ("notes", notes),
            ]:
                if val is not None:
                    updates.append(f"{col} = ?")
                    params.append(val)
            updates += ["visit_count = visit_count + 1", "updated_at = ?"]
            params += [now, session_id]
            conn.execute(
                f"UPDATE patients SET {', '.join(updates)} WHERE session_id = ?", params
            )
        else:
            conn.execute(
                "INSERT INTO patients "
                "(session_id, name, contact, last_service, notes, visit_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (session_id, name, contact, last_service, notes, now, now),
            )

        conn.commit()
        row = conn.execute("SELECT * FROM patients WHERE session_id = ?", (session_id,)).fetchone()
        conn.close()
        result = dict(row)
        print(f"[TOOL][CRM][OUTPUT] upsert_patient result={result}")
        return result


# ══════════════════════════════════════════════════════════════════════════════
# 2. Appointment Tool
# ══════════════════════════════════════════════════════════════════════════════

class AppointmentTool:
    """
    Manages dental appointments stored in SQLite.

    Schema:
      get_available_slots(limit) → list[dict]
      book_appointment(session_id, patient_name, contact, service, date, time) → dict
      get_patient_appointments(patient_name) → list[dict]
      cancel_appointment(appointment_id) → dict
    """

    name = "appointment"
    description = (
        "Book, retrieve, or cancel dental appointments. "
        "Call get_available_slots before booking to show real open slots. "
        "Call book_appointment once the patient confirms their chosen slot."
    )

    def get_available_slots(self, limit: int = 9) -> List[Dict[str, Any]]:
        """Return up to `limit` available (date, time, doctors) combos starting tomorrow."""
        print(f"[TOOL][APPOINTMENT][INPUT] get_available_slots limit={limit}")
        conn = _get_conn()
        today = datetime.now()
        slots: List[Dict[str, Any]] = []

        for delta in range(1, 15):
            if len(slots) >= limit:
                break
            d = today + timedelta(days=delta)
            day_name = d.strftime("%A")
            if day_name == "Sunday":
                continue
            date_str = d.strftime("%A, %d %B %Y")
            booked = {
                r["time"]
                for r in conn.execute(
                    "SELECT time FROM appointments WHERE date = ? AND status = 'confirmed'",
                    (date_str,),
                ).fetchall()
            }
            for t in AVAILABLE_TIMES:
                if t not in booked:
                    slots.append({
                        "date": date_str,
                        "time": t,
                        "doctors": DOCTOR_SCHEDULE.get(day_name, []),
                    })
                    if len(slots) >= limit:
                        break

        conn.close()
        print(f"[TOOL][APPOINTMENT][OUTPUT] get_available_slots count={len(slots)} slots={slots}")
        return slots

    def book_appointment(
        self,
        session_id: str,
        patient_name: str,
        contact: str,
        service: str,
        date: str,
        time: str,
    ) -> Dict[str, Any]:
        """Insert a confirmed appointment row; returns success/failure dict."""
        print(
            "[TOOL][APPOINTMENT][INPUT] book_appointment "
            f"session_id={session_id}, patient_name={patient_name}, contact={contact}, "
            f"service={service}, date={date}, time={time}"
        )
        conn = _get_conn()
        time = _normalize_time(time)
        day_name = date.split(",")[0].strip()
        doctors = DOCTOR_SCHEDULE.get(day_name, ["Available Doctor"])
        doctor = doctors[0]

        clash = conn.execute(
            "SELECT id FROM appointments WHERE date = ? AND time = ? AND status = 'confirmed'",
            (date, time),
        ).fetchone()
        if clash:
            conn.close()
            result = {
                "success": False,
                "message": f"Slot {date} at {time} is already taken. Please choose another.",
            }
            print(f"[TOOL][APPOINTMENT][OUTPUT] book_appointment result={result}")
            return result

        conn.execute(
            "INSERT INTO appointments "
            "(session_id, patient_name, contact, service, date, time, doctor, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed', ?)",
            (
                session_id, patient_name, contact, service,
                date, time, doctor, datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        appt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        saved_row = conn.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (appt_id,),
        ).fetchone()
        conn.close()
        result = {
            "success": True,
            "appointment_id": appt_id,
            "patient_name": patient_name,
            "service": service,
            "date": date,
            "time": time,
            "doctor": doctor,
            "message": (
                f"Appointment #{appt_id} confirmed for {patient_name} "
                f"on {date} at {time} with {doctor}."
            ),
        }
        if saved_row is not None:
            print(f"[TOOL][APPOINTMENT][DB] saved_row={dict(saved_row)}")
        print(f"[TOOL][APPOINTMENT][OUTPUT] book_appointment result={result}")
        return result

    def get_patient_appointments(self, patient_name: str) -> List[Dict[str, Any]]:
        print(f"[TOOL][APPOINTMENT][INPUT] get_patient_appointments patient_name={patient_name}")
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM appointments WHERE patient_name LIKE ? AND status = 'confirmed' "
            "ORDER BY created_at DESC LIMIT 5",
            (f"%{patient_name}%",),
        ).fetchall()
        conn.close()
        result = [dict(r) for r in rows]
        print(f"[TOOL][APPOINTMENT][OUTPUT] get_patient_appointments result={result}")
        return result

    def cancel_appointment(self, appointment_id: int) -> Dict[str, Any]:
        print(f"[TOOL][APPOINTMENT][INPUT] cancel_appointment appointment_id={appointment_id}")
        conn = _get_conn()
        conn.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE id = ?", (appointment_id,)
        )
        conn.commit()
        conn.close()
        result = {"success": True, "message": f"Appointment #{appointment_id} has been cancelled."}
        print(f"[TOOL][APPOINTMENT][OUTPUT] cancel_appointment result={result}")
        return result


# ══════════════════════════════════════════════════════════════════════════════
# 3. Weather Tool
# ══════════════════════════════════════════════════════════════════════════════

class WeatherTool:
    """
    Fetches current weather from wttr.in — no API key required.
    Useful for advising patients on travel conditions (e.g. heavy rain, heat warning).

    Schema:
      get_weather(city="Lahore") → dict
    """

    name = "weather"
    description = (
        "Get current weather for a city. "
        "Useful when a patient asks whether it is safe/comfortable to travel to the clinic."
    )

    def get_weather(self, city: str = "Lahore") -> Dict[str, Any]:
        print(f"[TOOL][WEATHER][INPUT] get_weather city={city}")
        try:
            resp = requests.get(
                f"https://wttr.in/{city}?format=j1",
                timeout=5,
                headers={"User-Agent": "DentaBot/1.0"},
            )
            if resp.status_code != 200:
                result = {"error": "Weather service unavailable", "city": city}
                print(f"[TOOL][WEATHER][OUTPUT] get_weather result={result}")
                return result
            data = resp.json()
            cur = data["current_condition"][0]
            result = {
                "city": city,
                "temperature_c": cur["temp_C"],
                "feels_like_c": cur["FeelsLikeC"],
                "description": cur["weatherDesc"][0]["value"],
                "humidity": cur["humidity"],
                "wind_kmph": cur["windspeedKmph"],
            }
            print(f"[TOOL][WEATHER][OUTPUT] get_weather result={result}")
            return result
        except Exception as exc:
            result = {"error": str(exc), "city": city}
            print(f"[TOOL][WEATHER][OUTPUT] get_weather result={result}")
            return result


# ══════════════════════════════════════════════════════════════════════════════
# 4. Dental Cost Tool
# ══════════════════════════════════════════════════════════════════════════════

class DentalCostTool:
    """
    Returns estimated PKR cost range for a dental procedure.
    Purely local — no network call needed.

    Schema:
      get_cost(procedure) → dict
    """

    name = "dental_cost"
    description = (
        "Return the estimated PKR cost range for a dental procedure or service at BrightSmile. "
        "Call when a patient asks 'how much does X cost' or 'what is the fee for Y'."
    )

    def get_cost(self, procedure: str) -> Dict[str, Any]:
        print(f"[TOOL][COST][INPUT] get_cost procedure={procedure}")
        lower = procedure.lower().strip()
        for key, cost in PROCEDURE_COSTS.items():
            if key in lower or lower in key:
                result = {
                    "procedure": key.title(),
                    "min_cost_pkr": cost["min"],
                    "max_cost_pkr": cost["max"],
                    "note": "Final cost may vary. Your insurance may cover part of the fee.",
                }
                print(f"[TOOL][COST][OUTPUT] get_cost result={result}")
                return result
        result = {
            "procedure": procedure,
            "message": "Exact cost unavailable for this procedure.",
            "note": "Please call 042-35001234 for a detailed quote.",
        }
        print(f"[TOOL][COST][OUTPUT] get_cost result={result}")
        return result
