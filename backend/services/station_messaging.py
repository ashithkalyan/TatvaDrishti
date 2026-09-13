"""
KAVACH Services — Station Messaging
========================================
Inter-station messaging (master-prompt review, section 6). Same
minimal-module pattern as audit_log.py / hotspot_ops.py.

SINGLE SOURCE OF TRUTH: police stations are NOT a new table here — this
project already has a real `Unit` table (55 real station names like
"Koramangala PS", "Whitefield PS", each tied to a real district),
already used elsewhere in the app (the document-ingestion confirm form,
see main.py's GET /api/meta/police-stations). Station messaging reads
the SAME table rather than inventing a second, disconnected station
list — exactly the "single source of truth" ground rule the project's
own architecture review calls for. Only the MESSAGES themselves are a
new table.
"""
import sqlite3
from datetime import datetime


def init_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS StationMessage (
            MessageID INTEGER PRIMARY KEY AUTOINCREMENT,
            FromUnitID INTEGER NOT NULL,
            ToUnitID INTEGER NOT NULL,
            SenderOfficerID INTEGER,
            MessageText TEXT NOT NULL,
            SentAt TEXT NOT NULL,
            IsRead INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (FromUnitID) REFERENCES Unit(UnitID),
            FOREIGN KEY (ToUnitID) REFERENCES Unit(UnitID)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stationmsg_thread ON StationMessage(FromUnitID, ToUnitID)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stationmsg_sentat ON StationMessage(SentAt)")
    conn.commit()


def list_stations(conn: sqlite3.Connection) -> list:
    """Every active real Unit (police station) — same rows the
    document-ingestion form's dropdown already uses."""
    rows = conn.execute("""
        SELECT u.UnitID, u.UnitName, d.DistrictName FROM Unit u
        JOIN District d ON u.DistrictID = d.DistrictID
        WHERE u.Active = 1 ORDER BY d.DistrictName, u.UnitName
    """).fetchall()
    return [{"unit_id": r[0], "unit_name": r[1], "district": r[2]} for r in rows]


def get_thread(conn: sqlite3.Connection, unit_a: int, unit_b: int, limit: int = 200) -> list:
    """Every message either direction between these two stations, oldest
    first — the frontend renders 'from unit_a' on one side and 'from
    unit_b' on the other, however the officer currently has the two
    dropdowns set."""
    rows = conn.execute("""
        SELECT sm.MessageID, sm.FromUnitID, sm.ToUnitID, sm.SenderOfficerID, u.Username,
               sm.MessageText, sm.SentAt, sm.IsRead
        FROM StationMessage sm
        LEFT JOIN Users u ON u.UserID = sm.SenderOfficerID
        WHERE (sm.FromUnitID = ? AND sm.ToUnitID = ?) OR (sm.FromUnitID = ? AND sm.ToUnitID = ?)
        ORDER BY sm.SentAt ASC LIMIT ?
    """, (unit_a, unit_b, unit_b, unit_a, limit)).fetchall()
    return [{
        "message_id": r[0], "from_unit_id": r[1], "to_unit_id": r[2],
        "sender_officer_id": r[3], "sender_username": r[4],
        "text": r[5], "sent_at": r[6], "is_read": bool(r[7]),
    } for r in rows]


def send_message(conn: sqlite3.Connection, from_unit: int, to_unit: int, sender_officer_id: int, text: str) -> int:
    cur = conn.execute(
        "INSERT INTO StationMessage (FromUnitID, ToUnitID, SenderOfficerID, MessageText, SentAt, IsRead) "
        "VALUES (?,?,?,?,?,0)",
        (from_unit, to_unit, sender_officer_id, text, datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def mark_thread_read(conn: sqlite3.Connection, reader_unit: int, other_unit: int):
    """Marks every message INTO reader_unit (i.e. sent BY the other
    station) as read — mirrors normal chat-app semantics: opening a
    thread reads the other side's messages, not your own."""
    conn.execute(
        "UPDATE StationMessage SET IsRead = 1 WHERE FromUnitID = ? AND ToUnitID = ? AND IsRead = 0",
        (other_unit, reader_unit),
    )
    conn.commit()


def unread_count(conn: sqlite3.Connection, unit_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM StationMessage WHERE ToUnitID = ? AND IsRead = 0", (unit_id,)
    ).fetchone()
    return row[0] if row else 0


def total_unread_for_officer(conn: sqlite3.Connection) -> int:
    """App-wide unread count across ALL stations — powers the header
    notification badge without the officer needing to have picked a
    'my station' yet."""
    row = conn.execute("SELECT COUNT(*) FROM StationMessage WHERE IsRead = 0").fetchone()
    return row[0] if row else 0
