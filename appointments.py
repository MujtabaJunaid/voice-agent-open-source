"""SQLite-backed clinic schedule used by the bot's booking tools."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "clinic.db"

SLOTS = ["09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"]


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def available_slots(date: str) -> list[str]:
    with sqlite3.connect(DB_PATH) as conn:
        taken = {row[0] for row in conn.execute(
            "SELECT time FROM appointments WHERE date = ?", (date,)
        )}
    return [slot for slot in SLOTS if slot not in taken]


def recent(limit: int = 20) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM appointments ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def book(patient_name: str, reason: str, date: str, time: str) -> dict:
    if time not in SLOTS:
        return {"ok": False, "error": f"{time} is not a bookable slot. Valid slots: {', '.join(SLOTS)}"}
    with sqlite3.connect(DB_PATH) as conn:
        taken = {row[0] for row in conn.execute(
            "SELECT time FROM appointments WHERE date = ?", (date,)
        )}
        if time in taken:
            return {"ok": False, "error": f"{time} on {date} is already booked. Offer another slot."}
        cur = conn.execute(
            "INSERT INTO appointments (patient_name, reason, date, time, created_at) VALUES (?, ?, ?, ?, ?)",
            (patient_name, reason, date, time, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {
            "ok": True,
            "appointment_id": cur.lastrowid,
            "patient_name": patient_name,
            "reason": reason,
            "date": date,
            "time": time,
        }
