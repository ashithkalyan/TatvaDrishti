"""
KAVACH Services — Police Intelligence Notice Board
=======================================================
Daily / Monthly / Yearly intelligence bulletin (master-prompt review,
sections 4-5). Every field here is a real query against this project's
own CENTRAL dataset (vw_fir_flat, PersonIdentity) — never placeholder
or invented content. No images are generated or fabricated here: the
frontend renders a neutral silhouette/initials placeholder for every
profile (see components/NoticeBoard.jsx), consistent with this
project's synthetic-data-only ground rule and specifically because
this build does not attach real or scraped photographs to any
individual, named or not.

Three views share one shape (see get_feed()) so the frontend can render
all three with the same component, just a different date_filter.
"""
import sqlite3
from datetime import datetime


def _date_filter(view: str, ref_date: str):
    if view == "month":
        return "strftime('%Y-%m', registration_date) = strftime('%Y-%m', ?)"
    if view == "year":
        return "strftime('%Y', registration_date) = strftime('%Y', ?)"
    return "registration_date = ?"  # day


def latest_data_date(conn: sqlite3.Connection) -> str:
    """The most recent registration_date actually on file. Used as the
    default anchor for day/month views instead of the real wall-clock
    date — this is a frozen synthetic dataset (see seed_data.py), so
    "today" in the real world usually has zero rows and would make the
    Daily tab look broken by default. Anchoring to the latest REAL date
    in the data keeps every number here still 100% grounded — it just
    picks a more useful reference point than an arbitrary date that
    predates this feature's own build."""
    row = conn.execute("SELECT MAX(registration_date) FROM vw_fir_flat").fetchone()
    return row[0] if row and row[0] else datetime.now().strftime("%Y-%m-%d")


def get_feed(conn: sqlite3.Connection, view: str = "day", ref_date: str = None) -> dict:
    ref_date = ref_date or latest_data_date(conn)
    where = _date_filter(view, ref_date)
    params = (ref_date,)

    total_firs = conn.execute(f"SELECT COUNT(*) FROM vw_fir_flat WHERE {where}", params).fetchone()[0]
    arrests = conn.execute(f"""
        SELECT COUNT(*) FROM ArrestSurrender arr
        JOIN CaseMaster cm ON cm.CaseMasterID = arr.CaseMasterID
        WHERE {_date_filter(view, ref_date).replace('registration_date', 'cm.CrimeRegisteredDate')}
    """, params).fetchone()[0]
    weapon_cases = conn.execute(f"""
        SELECT COUNT(*) FROM vw_fir_flat
        WHERE {where} AND weapon_used IS NOT NULL AND weapon_used != '' AND weapon_used != 'None'
    """, params).fetchone()[0]
    gang_linked = conn.execute(f"""
        SELECT COUNT(DISTINCT cm.CaseMasterID) FROM CaseMaster cm
        JOIN Accused a ON a.CaseMasterID = cm.CaseMasterID
        JOIN PersonIdentityLink pil ON pil.AccusedMasterID = a.AccusedMasterID
        JOIN PersonIdentity pi ON pi.PersonIdentityID = pil.PersonIdentityID
        WHERE pi.GangAffiliation IS NOT NULL AND pi.GangAffiliation != ''
          AND {_date_filter(view, ref_date).replace('registration_date', 'cm.CrimeRegisteredDate')}
    """, params).fetchone()[0]

    recent_cases = conn.execute(f"""
        SELECT fir_number, district, police_station, crime_type, registration_date, status, crime_description, gravity
        FROM vw_fir_flat WHERE {where}
        ORDER BY registration_date DESC, fir_id DESC LIMIT 12
    """, params).fetchall()

    urgent_notices = conn.execute(f"""
        SELECT fir_number, district, crime_type, registration_date, weapon_used, gravity, crime_description
        FROM vw_fir_flat
        WHERE {where} AND (
            gravity IN ('Heinous', 'Serious', 'Grave')
            OR (weapon_used IS NOT NULL AND weapon_used != '' AND weapon_used != 'None')
        )
        ORDER BY registration_date DESC LIMIT 8
    """, params).fetchall()

    # Featured profiles: a persistent high-alert roster, not date-scoped
    # (the point is "who KAVACH is watching right now", the same on every
    # day/month/year view) — each with their most recent linked FIR for
    # the "crime committed + FIR no." click-through.
    featured_rows = conn.execute("""
        SELECT pi.PersonIdentityID, pi.CanonicalName, pi.RiskCategory, pi.GangAffiliation,
               pi.ModusOperandi, d.DistrictName,
               (SELECT cm.CrimeNo FROM Accused a2
                JOIN PersonIdentityLink pil2 ON pil2.AccusedMasterID = a2.AccusedMasterID
                JOIN CaseMaster cm ON cm.CaseMasterID = a2.CaseMasterID
                WHERE pil2.PersonIdentityID = pi.PersonIdentityID
                ORDER BY cm.CrimeRegisteredDate DESC LIMIT 1) AS latest_fir,
               (SELECT csh.CrimeHeadName FROM Accused a3
                JOIN PersonIdentityLink pil3 ON pil3.AccusedMasterID = a3.AccusedMasterID
                JOIN CaseMaster cm3 ON cm3.CaseMasterID = a3.CaseMasterID
                JOIN CrimeSubHead csh ON cm3.CrimeMinorHeadID = csh.CrimeSubHeadID
                WHERE pil3.PersonIdentityID = pi.PersonIdentityID
                ORDER BY cm3.CrimeRegisteredDate DESC LIMIT 1) AS latest_crime_type
        FROM PersonIdentity pi
        LEFT JOIN District d ON pi.DistrictID = d.DistrictID
        WHERE pi.RiskCategory IN ('EXTREME', 'HIGH')
        ORDER BY pi.RiskScore DESC LIMIT 10
    """).fetchall()

    return {
        "view": view,
        "date": ref_date,
        "headline_stats": {
            "total_firs": total_firs, "arrests": arrests,
            "weapon_involved_cases": weapon_cases, "gang_linked_cases": gang_linked,
        },
        "urgent_notices": [{
            "fir_number": r[0], "district": r[1], "crime_type": r[2], "date": r[3],
            "weapon_used": r[4], "gravity": r[5], "brief": (r[6] or "")[:160],
        } for r in urgent_notices],
        "recent_cases": [{
            "fir_number": r[0], "district": r[1], "police_station": r[2], "crime_type": r[3],
            "date": r[4], "status": r[5], "brief": (r[6] or "")[:160], "gravity": r[7],
        } for r in recent_cases],
        "featured_profiles": [{
            "person_id": r[0], "name": r[1], "risk_category": r[2], "gang_affiliation": r[3],
            "modus_operandi": r[4], "district": r[5], "latest_fir_number": r[6], "latest_crime_type": r[7],
        } for r in featured_rows],
    }
