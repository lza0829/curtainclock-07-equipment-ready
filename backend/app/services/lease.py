from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from app.services.ready import readiness, resource_busy


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bump(conn: sqlite3.Connection, key: str, delta: int) -> int:
    row = conn.execute("SELECT value FROM watermarks WHERE key=?", (key,)).fetchone()
    cur = int(row["value"]) if row else 0
    nxt = cur + delta
    conn.execute(
        "INSERT INTO watermarks(key, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, nxt, _now()),
    )
    return nxt


def _conflict_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT value FROM settings WHERE key='conflict_mode'"
    ).fetchone()
    return row["value"] if row else "reject"


def bypass_inflight(conn: sqlite3.Connection) -> int:
    """旁路在途计数：与租约旁路标记同源（status='open' 且 bypass=1 的租约数）。

    不另设水位——开窗落标记租约、关窗改租约状态都与计数同事务，
    总览读数与「租约页·仅看旁路」过滤天然一致，不会漂移。
    """
    return conn.execute(
        "SELECT COUNT(*) c FROM leases WHERE status='open' AND bypass=1"
    ).fetchone()["c"]


def open_lease(conn: sqlite3.Connection, session_code: str) -> dict:
    session = conn.execute(
        "SELECT * FROM sessions WHERE code=?", (session_code,)
    ).fetchone()
    if session is None:
        raise ValueError(f"批窗不存在：{session_code}")
    if session["status"] == "live":
        raise ValueError("批窗已在上课，勿重复开窗")
    if session["status"] == "done":
        raise ValueError("批窗已结束")

    ready = readiness(conn, session)
    if ready["resource_reasons"]:
        # 硬冲突（算力槽/执行器停用或被占）：拒绝开窗，落冲突水位，不落租约
        mode = _conflict_mode(conn)
        for reason in ready["resource_reasons"]:
            kind = "room" if "算力槽" in reason else "teacher"
            resource = (
                session["room_code"]
                if kind == "room"
                else session["teacher_code"]
            )
            conn.execute(
                "INSERT INTO conflicts(kind, session_code, resource_code, day, start_min, end_min, reason, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    kind,
                    session_code,
                    resource,
                    session["day"],
                    session["start_min"],
                    session["end_min"],
                    reason,
                    _now(),
                ),
            )
            _bump(conn, "conflict_count", 1)
        # 底座贯彻 reject（冲突落库后由调用方提交）；候补算力槽留给后续题
        return {
            "ok": False,
            "error": "；".join(ready["resource_reasons"]),
            "conflict_mode": mode,
        }

    if resource_busy(
        conn,
        kind="room",
        resource_code=session["room_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
    ) or resource_busy(
        conn,
        kind="teacher",
        resource_code=session["teacher_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
    ):
        raise ValueError("资源刚被占用，开窗失败")

    # 全局架构 = 缺依赖旁路占用：缺依赖不拒开窗，但必须同事务——
    # 落 open 租约、批窗/租约打旁路标记并快照缺失依赖、旁路在途计数随标记租约 +1。
    # 齐套窗则正常开窗（bypass=0）。缺依赖却无标记的静默成功在结构上不可能。
    missing = ready["missing_deps"]
    bypass = 1 if missing else 0
    n = conn.execute("SELECT COUNT(*) c FROM leases").fetchone()["c"] + 1
    lease_no = f"L-{session['day'].replace('-', '')}-{n:04d}"
    conn.execute(
        "INSERT INTO leases(lease_no, session_code, room_code, teacher_code, day, start_min, end_min, status, opened_at, bypass, missing_deps) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            lease_no,
            session_code,
            session["room_code"],
            session["teacher_code"],
            session["day"],
            session["start_min"],
            session["end_min"],
            "open",
            _now(),
            bypass,
            json.dumps(missing, ensure_ascii=False),
        ),
    )
    conn.execute(
        "UPDATE sessions SET status='live', bypass=? WHERE code=?",
        (bypass, session_code),
    )
    open_n = _bump(conn, "open_leases", 1)
    return {
        "ok": True,
        "lease_no": lease_no,
        "session_code": session_code,
        "status": "open",
        "open_leases": open_n,
        "bypass": bool(bypass),
        "missing_deps": missing,
        "bypass_inflight": bypass_inflight(conn),
    }


def close_lease(conn: sqlite3.Connection, lease_no: str) -> dict:
    lease = conn.execute(
        "SELECT * FROM leases WHERE lease_no=?", (lease_no,)
    ).fetchone()
    if lease is None:
        raise ValueError(f"租约不存在：{lease_no}")
    if lease["status"] != "open":
        raise ValueError("租约不在占用态")
    conn.execute(
        "UPDATE leases SET status='closed', closed_at=? WHERE lease_no=?",
        (_now(), lease_no),
    )
    conn.execute(
        "UPDATE sessions SET status='done' WHERE code=?",
        (lease["session_code"],),
    )
    # 占用与旁路计数同事务同减：open_leases 水位 -1，
    # 旁路在途随该租约离开 open 态同步 -1（同源派生，无需另减）。
    open_n = _bump(conn, "open_leases", -1)
    return {
        "lease_no": lease_no,
        "status": "closed",
        "open_leases": open_n,
        "was_bypass": bool(lease["bypass"]),
        "bypass_inflight": bypass_inflight(conn),
    }
