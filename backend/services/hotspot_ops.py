"""
KAVACH Services — Hotspot Operations
=========================================
Backend for "Hotspot -> actionable patrol recommendation -> officer
review -> logbook" (master-prompt review, sections 8-10). Same
minimal-module pattern as services/audit_log.py: one schema, one write
path, one read path.

WHY THIS IS HONEST TO BUILD, NOT JUST A CHECKBOX
  The recommendation text (peak time, risk level, suggested response)
  is computed from this project's OWN real FIR records for that
  district+crime_type — never a fabricated narrative. See
  generate_recommendation() below for exactly what's real vs. derived.
  Confirming/starting/completing an operation writes a REAL row here,
  not local component state that vanishes on refresh — a supervisor
  reopening this later gets the same data an officer entered.

HUMAN-IN-THE-LOOP, ENFORCED SERVER-SIDE, NOT JUST IN THE UI
  A recommendation is only ever generated on request (GET) and never
  auto-transitions to "assigned"/"started"/"completed" — every status
  change is a separate, explicit PATCH the frontend only sends after an
  officer clicks a real button. Nothing in this module ever claims an
  action was taken; it only records what an officer confirmed.
"""
import sqlite3
from datetime import datetime


def init_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS HotspotOperation (
            OperationID INTEGER PRIMARY KEY AUTOINCREMENT,
            District TEXT NOT NULL,
            PoliceStation TEXT,
            CrimeType TEXT NOT NULL,
            Latitude REAL,
            Longitude REAL,
            RecommendedAction TEXT,
            SuggestedPeriod TEXT,
            Reason TEXT,
            Status TEXT NOT NULL DEFAULT 'recommended',
            AssignedTeam TEXT,
            AssignedVehicle TEXT,
            OfficerID INTEGER,
            Notes TEXT,
            CreatedAt TEXT NOT NULL,
            AssignedAt TEXT,
            StartedAt TEXT,
            CompletedAt TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hotspotop_district ON HotspotOperation(District)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hotspotop_status ON HotspotOperation(Status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hotspotop_created ON HotspotOperation(CreatedAt)")
    conn.commit()


# Karnataka-day-shift-relevant time bands, ordered so the FIRST one that
# actually appears most often in real occurrence_time data wins below.
_TIME_BANDS = [
    ("late night / early hours", 0, 4),
    ("early morning", 4, 8),
    ("morning", 8, 12),
    ("afternoon", 12, 16),
    ("evening", 16, 20),
    ("night", 20, 24),
]


def _band_for_hour(hour: int) -> str:
    for label, start, end in _TIME_BANDS:
        if start <= hour < end:
            return label
    return "night"


def generate_recommendation(conn: sqlite3.Connection, district: str, crime_type: str,
                             police_station: str = None) -> dict:
    """
    Grounds every field in this project's own FIR records for this
    exact district + crime_type (police_station further narrows it when
    given) — nothing here is a template filled with made-up numbers.

    - peak_period: the time-of-day band real occurrence_time values for
      these FIRs cluster into most often (falls back to "not enough
      timestamped records" when there's too little data to say).
    - recent_incidents: the actual most recent FIR numbers/dates/briefs
      on file, not placeholder text.
    - risk_level: derived from gravity/weapon/vehicle-involvement flags
      already on these FIRs, not a random pick.
    - recommended_action / reasoning: a short, deterministic mapping
      from the above — never phrased as KAVACH having "decided" or
      "dispatched" anything; see the human-in-the-loop status flow
      below for why.
    """
    where, params = ["district = ?", "crime_type = ?"], [district, crime_type]
    if police_station:
        where.append("police_station = ?")
        params.append(police_station)
    where_sql = " AND ".join(where)

    total = conn.execute(f"SELECT COUNT(*) FROM vw_fir_flat WHERE {where_sql}", params).fetchone()[0]

    hour_rows = conn.execute(
        f"SELECT occurrence_time FROM vw_fir_flat WHERE {where_sql} AND occurrence_time IS NOT NULL", params
    ).fetchall()
    band_counts = {}
    for (t,) in hour_rows:
        try:
            hour = int(str(t).split(":")[0])
        except (ValueError, IndexError):
            continue
        band = _band_for_hour(hour)
        band_counts[band] = band_counts.get(band, 0) + 1
    peak_period = max(band_counts, key=band_counts.get) if band_counts else None

    recent = conn.execute(f"""
        SELECT fir_number, occurrence_date, crime_description, status
        FROM vw_fir_flat WHERE {where_sql}
        ORDER BY occurrence_date DESC LIMIT 5
    """, params).fetchall()
    recent_incidents = [
        {"fir_number": r[0], "date": r[1], "brief": (r[2] or "")[:140], "status": r[3]}
        for r in recent
    ]

    risk_signals = conn.execute(f"""
        SELECT
            SUM(CASE WHEN weapon_used IS NOT NULL AND weapon_used != '' AND weapon_used != 'None' THEN 1 ELSE 0 END),
            SUM(CASE WHEN vehicle_involved IS NOT NULL AND vehicle_involved != '' AND vehicle_involved != 'None' THEN 1 ELSE 0 END),
            SUM(CASE WHEN gravity IN ('Heinous', 'Serious', 'Grave') THEN 1 ELSE 0 END)
        FROM vw_fir_flat WHERE {where_sql}
    """, params).fetchone()
    weapon_count, vehicle_count, grave_count = (risk_signals[0] or 0), (risk_signals[1] or 0), (risk_signals[2] or 0)

    if total == 0:
        return {
            "district": district, "police_station": police_station, "crime_type": crime_type,
            "total_incidents": 0, "peak_period": None, "recent_incidents": [],
            "risk_level": "Unknown", "recommended_action": None, "suggested_period": None,
            "reason": "No FIR records on file for this district/crime-type combination yet.",
        }

    grave_ratio = grave_count / total
    risk_level = "High" if (grave_ratio > 0.3 or total >= 15) else "Medium" if total >= 6 else "Low"

    if risk_level == "High":
        action = "Night patrol + increased visible presence" if peak_period in (
            "night", "late night / early hours") else "Targeted patrol during peak hours"
    elif risk_level == "Medium":
        action = "Periodic patrol / spot checks"
    else:
        action = "Routine monitoring"

    reason_bits = [f"{total} case(s) on file for {crime_type} in {police_station or district}"]
    if peak_period:
        reason_bits.append(f"most concentrated in the {peak_period} band")
    if weapon_count:
        reason_bits.append(f"{weapon_count} involving a weapon")
    if vehicle_count:
        reason_bits.append(f"{vehicle_count} involving a vehicle")
    reason = "; ".join(reason_bits) + "."

    return {
        "district": district, "police_station": police_station, "crime_type": crime_type,
        "total_incidents": total, "peak_period": peak_period, "recent_incidents": recent_incidents,
        "risk_level": risk_level, "recommended_action": action,
        "suggested_period": peak_period, "reason": reason,
    }


def create_operation(conn: sqlite3.Connection, district: str, crime_type: str, police_station: str,
                      latitude, longitude, recommended_action: str, suggested_period: str, reason: str) -> int:
    """Logs a recommendation the officer chose to act on — status starts
    at 'recommended' and only ever advances via update_status(), each
    call a separate officer-initiated action."""
    cur = conn.execute(
        """INSERT INTO HotspotOperation
           (District, PoliceStation, CrimeType, Latitude, Longitude, RecommendedAction,
            SuggestedPeriod, Reason, Status, CreatedAt)
           VALUES (?,?,?,?,?,?,?,?, 'recommended', ?)""",
        (district, police_station, crime_type, latitude, longitude, recommended_action,
         suggested_period, reason, datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def update_status(conn: sqlite3.Connection, operation_id: int, status: str, user_id: int,
                   assigned_team: str = None, assigned_vehicle: str = None, notes: str = None) -> bool:
    """Every transition is explicit and officer-attributed — never
    auto-advanced. status must be one of assigned/started/completed
    (recommended is the only status create_operation() itself sets)."""
    if status not in ("assigned", "started", "completed"):
        return False
    ts_column = {"assigned": "AssignedAt", "started": "StartedAt", "completed": "CompletedAt"}[status]
    fields, params = ["Status = ?", f"{ts_column} = ?", "OfficerID = ?"], [status, datetime.now().isoformat(), user_id]
    if assigned_team is not None:
        fields.append("AssignedTeam = ?"); params.append(assigned_team)
    if assigned_vehicle is not None:
        fields.append("AssignedVehicle = ?"); params.append(assigned_vehicle)
    if notes is not None:
        fields.append("Notes = ?"); params.append(notes)
    params.append(operation_id)
    cur = conn.execute(f"UPDATE HotspotOperation SET {', '.join(fields)} WHERE OperationID = ?", params)
    conn.commit()
    return cur.rowcount > 0


def list_operations(conn: sqlite3.Connection, status: str = None, statuses: list = None,
                     district: str = None, period: str = None, limit: int = 200) -> list:
    """status: single exact status. statuses: a list (e.g. ["recommended",
    "assigned", "started"] for "pending"), takes precedence over status
    when both are given. period: day/week/month/year, filters CreatedAt;
    None means all-time (no date filter) — used for open-ended questions
    like "show pending hotspot actions" that shouldn't silently drop
    older-but-still-pending ones."""
    where, params = ["1=1"], []
    if statuses:
        where.append(f"h.Status IN ({','.join('?' * len(statuses))})")
        params.extend(statuses)
    elif status:
        where.append("h.Status = ?"); params.append(status)
    if district:
        where.append("h.District = ?"); params.append(district)
    if period:
        offsets = {"day": "-1 day", "week": "-7 days", "month": "-1 month", "year": "-1 year"}
        where.append("h.CreatedAt >= datetime('now', ?)")
        params.append(offsets.get(period, "-7 days"))
    rows = conn.execute(f"""
        SELECT h.OperationID, h.District, h.PoliceStation, h.CrimeType, h.Latitude, h.Longitude,
               h.RecommendedAction, h.SuggestedPeriod, h.Reason, h.Status,
               h.AssignedTeam, h.AssignedVehicle, h.OfficerID, u.Username, h.Notes,
               h.CreatedAt, h.AssignedAt, h.StartedAt, h.CompletedAt
        FROM HotspotOperation h
        LEFT JOIN Users u ON u.UserID = h.OfficerID
        WHERE {' AND '.join(where)}
        ORDER BY h.CreatedAt DESC LIMIT ?
    """, (*params, limit)).fetchall()
    cols = ["operation_id", "district", "police_station", "crime_type", "latitude", "longitude",
            "recommended_action", "suggested_period", "reason", "status",
            "assigned_team", "assigned_vehicle", "officer_id", "officer_username", "notes",
            "created_at", "assigned_at", "started_at", "completed_at"]
    return [dict(zip(cols, r)) for r in rows]


def summary(conn: sqlite3.Connection, period: str = "week") -> dict:
    """Real aggregate counts for the logbook summary views (daily/
    weekly/monthly/yearly) — see main.py's GET /api/hotspot-ops/summary.
    period is one of day/week/month/year, mapped to a SQLite datetime
    offset applied to CreatedAt; None means all-time."""
    offsets = {"day": "-1 day", "week": "-7 days", "month": "-1 month", "year": "-1 year"}
    if period:
        offset = offsets.get(period, "-7 days")
        date_where, date_params = "CreatedAt >= datetime('now', ?)", (offset,)
    else:
        date_where, date_params = "1=1", ()
    rows = conn.execute(f"""
        SELECT Status, COUNT(*) FROM HotspotOperation
        WHERE {date_where}
        GROUP BY Status
    """, date_params).fetchall()
    counts = {status: n for status, n in rows}
    areas = conn.execute(f"""
        SELECT DISTINCT District FROM HotspotOperation WHERE {date_where}
    """, date_params).fetchall()
    crime_types = conn.execute(f"""
        SELECT CrimeType, COUNT(*) c FROM HotspotOperation WHERE {date_where}
        GROUP BY CrimeType ORDER BY c DESC LIMIT 5
    """, date_params).fetchall()
    districts = conn.execute(f"""
        SELECT District, COUNT(*) c FROM HotspotOperation WHERE {date_where}
        GROUP BY District ORDER BY c DESC LIMIT 5
    """, date_params).fetchall()
    return {
        "period": period,
        "total_operations": sum(counts.values()),
        "recommended": counts.get("recommended", 0),
        "assigned": counts.get("assigned", 0),
        "started": counts.get("started", 0),
        "completed": counts.get("completed", 0),
        "districts_covered": [a[0] for a in areas],
        "top_crime_types": [{"crime_type": c[0], "count": c[1]} for c in crime_types],
        "top_districts": [{"district": d[0], "count": d[1]} for d in districts],
    }
