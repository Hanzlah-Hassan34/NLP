"""
CRM Tool — interactive demo runner for the evaluation report.

Runs the pytest suite for the CRM tool, then performs a small live
demonstration of CRUD operations so the report can show both:
  (a) the green test results, and
  (b) actual data going in and out of the CRM.

Usage:
    python evals/demo_tool_crm.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tools import CRMTool


def banner(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  {title}\n{bar}")


def run_pytest() -> int:
    banner("STEP 1 - pytest unit tests for evals/test_tools_crm.py")
    cmd = [
        sys.executable, "-m", "pytest",
        "evals/test_tools_crm.py", "-v", "--tb=short", "--no-header",
        "-W", "ignore::DeprecationWarning",
        "-W", "ignore::pytest.PytestUnknownMarkWarning",
    ]
    return subprocess.call(cmd)


def run_demo() -> None:
    banner("STEP 2 - live CRUD demonstration")
    crm = CRMTool()
    sid = f"demo-{uuid.uuid4().hex[:8]}"
    print(f"Using session_id = {sid}\n")

    # CREATE
    print("[CREATE] crm.upsert_patient(session_id, name='Ali Khan', "
          "contact='0301-1234567', last_service='cleaning')")
    crm.upsert_patient(sid, name="Ali Khan", contact="0301-1234567",
                       last_service="cleaning")
    rec = crm.get_patient(sid)
    print(f"  -> stored record: {json.dumps(rec, indent=2, default=str)}")

    # READ
    print("\n[READ] crm.get_patient(session_id)")
    rec = crm.get_patient(sid)
    print(f"  -> name={rec.get('name')}  contact={rec.get('contact')}  "
          f"visits={rec.get('visit_count')}  "
          f"last_service={rec.get('last_service')}")

    # UPDATE name + contact
    print("\n[UPDATE] crm.upsert_patient(session_id, name='Ali Khan Updated', "
          "contact='0321-9999999')")
    crm.upsert_patient(sid, name="Ali Khan Updated", contact="0321-9999999")
    rec = crm.get_patient(sid)
    print(f"  -> name={rec.get('name')}  contact={rec.get('contact')}  "
          f"visits={rec.get('visit_count')}")

    # UPDATE last_service (and confirm visit count increments where applicable)
    print("\n[UPDATE] crm.upsert_patient(session_id, last_service='whitening')")
    crm.upsert_patient(sid, last_service="whitening")
    rec = crm.get_patient(sid)
    print(f"  -> last_service={rec.get('last_service')}  "
          f"visits={rec.get('visit_count')}")

    # PERSISTENCE
    print("\n[PERSISTENCE] new CRMTool() instance, same session_id")
    crm2 = CRMTool()
    rec2 = crm2.get_patient(sid)
    print(f"  -> reloaded: name={rec2.get('name')}  "
          f"contact={rec2.get('contact')}  "
          f"last_service={rec2.get('last_service')}")
    assert rec2.get("name") == "Ali Khan Updated", "persistence broken"
    print("  OK: data survived across CRMTool instances.")

    # NEGATIVE
    print("\n[READ-NEG] crm.get_patient('nonexistent-session')")
    none_rec = crm.get_patient("nonexistent-session")
    print(f"  -> {none_rec}")

    # CLEANUP
    print("\n[CLEANUP] removing demo record")
    import sqlite3, os
    db_path = os.getenv("DENTABOT_DB_PATH", "dentabot.db")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM patients WHERE session_id = ?", (sid,))
        conn.commit(); conn.close()
        print("  done.")
    except Exception as exc:
        print(f"  cleanup skipped: {exc}")

    banner("CRM TOOL EVALUATION COMPLETE")


def main() -> int:
    rc = run_pytest()
    if rc != 0:
        print("\n[!] pytest reported failures — see output above.")
        return rc
    run_demo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
