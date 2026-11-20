from __future__ import annotations

from fastapi import APIRouter

from app.db import connect
from app.services.lease import bypass_inflight

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard():
    conn = connect()
    try:
        day_row = conn.execute(
            "SELECT value FROM settings WHERE key='fixture_day'"
        ).fetchone()
        day = day_row["value"] if day_row else None
        open_leases = conn.execute(
            "SELECT value FROM watermarks WHERE key='open_leases'"
        ).fetchone()
        conflicts = conn.execute(
            "SELECT value FROM watermarks WHERE key='conflict_count'"
        ).fetchone()
        live_n = conn.execute(
            "SELECT COUNT(*) c FROM sessions WHERE status='live'"
        ).fetchone()["c"]
        draft_n = conn.execute(
            "SELECT COUNT(*) c FROM sessions WHERE status='draft'"
        ).fetchone()["c"]
        # 旁路在途与租约旁路标记同源派生（open 且 bypass=1）
        bypass_open = bypass_inflight(conn)
        bypass_total = conn.execute(
            "SELECT COUNT(*) c FROM leases WHERE bypass=1"
        ).fetchone()["c"]
        deps_down = conn.execute(
            "SELECT COUNT(*) c FROM datasets WHERE available=0"
        ).fetchone()["c"]
        return {
            "fixture_day": day,
            "open_leases": int(open_leases["value"]) if open_leases else 0,
            "conflict_count": int(conflicts["value"]) if conflicts else 0,
            "bypass_inflight": bypass_open,
            "bypass_total": bypass_total,
            "datasets_unavailable": deps_down,
            "live_sessions": live_n,
            "draft_sessions": draft_n,
        }
    finally:
        conn.close()
