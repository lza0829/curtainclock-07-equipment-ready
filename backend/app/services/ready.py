from __future__ import annotations

import sqlite3


def room_active(conn: sqlite3.Connection, room_code: str) -> bool:
    row = conn.execute(
        "SELECT active FROM rooms WHERE code=?", (room_code,)
    ).fetchone()
    return bool(row and row["active"] == 1)


def teacher_active(conn: sqlite3.Connection, teacher_code: str) -> bool:
    row = conn.execute(
        "SELECT active FROM teachers WHERE code=?", (teacher_code,)
    ).fetchone()
    return bool(row and row["active"] == 1)


def overlap(
    a_start: int, a_end: int, b_start: int, b_end: int
) -> bool:
    return a_start < b_end and b_start < a_end


def resource_busy(
    conn: sqlite3.Connection,
    *,
    kind: str,
    resource_code: str,
    day: str,
    start_min: int,
    end_min: int,
    exclude_session: str | None = None,
) -> sqlite3.Row | None:
    col = "room_code" if kind == "room" else "teacher_code"
    rows = conn.execute(
        f"SELECT * FROM leases WHERE {col}=? AND day=? AND status='open'",
        (resource_code, day),
    ).fetchall()
    for r in rows:
        if exclude_session and r["session_code"] == exclude_session:
            continue
        if overlap(start_min, end_min, r["start_min"], r["end_min"]):
            return r
    return None


def declared_deps(conn: sqlite3.Connection, session_code: str) -> list[str]:
    """批窗声明的上游依赖数据集编码。"""
    rows = conn.execute(
        "SELECT dataset_code FROM session_deps WHERE session_code=? "
        "ORDER BY dataset_code",
        (session_code,),
    ).fetchall()
    return [r["dataset_code"] for r in rows]


def dataset_available(conn: sqlite3.Connection, dataset_code: str) -> bool:
    row = conn.execute(
        "SELECT available FROM datasets WHERE code=?", (dataset_code,)
    ).fetchone()
    return bool(row and row["available"] == 1)


def missing_deps(conn: sqlite3.Connection, session_code: str) -> list[str]:
    """已声明但台账不可用（含未登记）的依赖，按编码排序。"""
    return [
        c for c in declared_deps(conn, session_code)
        if not dataset_available(conn, c)
    ]


def dep_details(conn: sqlite3.Connection, session_code: str) -> list[dict]:
    """声明依赖的台账快照（供批窗页/就绪接口展示）。"""
    rows = conn.execute(
        "SELECT sd.dataset_code AS code, ds.name AS name, ds.available AS available "
        "FROM session_deps sd LEFT JOIN datasets ds ON ds.code = sd.dataset_code "
        "WHERE sd.session_code=? ORDER BY sd.dataset_code",
        (session_code,),
    ).fetchall()
    return [
        {
            "code": r["code"],
            "name": r["name"] or r["code"],
            "available": bool(r["available"]),
        }
        for r in rows
    ]


def readiness(conn: sqlite3.Connection, session: sqlite3.Row) -> dict:
    """就绪判定：资源原因（硬冲突，拒）与缺失依赖（旁路臂）分列。

    ready=True 当且仅当资源可用且声明依赖齐套；调用方与开窗同事务读取，
    依赖变更与开窗并发不会读到假齐套。
    """
    resource_reasons: list[str] = []
    if not room_active(conn, session["room_code"]):
        resource_reasons.append("算力槽未启用")
    if not teacher_active(conn, session["teacher_code"]):
        resource_reasons.append("执行器未启用")
    busy_room = resource_busy(
        conn,
        kind="room",
        resource_code=session["room_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
        exclude_session=session["code"],
    )
    if busy_room:
        resource_reasons.append(f"算力槽已被租约 {busy_room['lease_no']} 占用")
    busy_teacher = resource_busy(
        conn,
        kind="teacher",
        resource_code=session["teacher_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
        exclude_session=session["code"],
    )
    if busy_teacher:
        resource_reasons.append(f"执行器已被租约 {busy_teacher['lease_no']} 占用")
    deps_missing = missing_deps(conn, session["code"])
    dep_reasons = [f"依赖数据集不可用：{c}" for c in deps_missing]
    return {
        "ready": not resource_reasons and not deps_missing,
        "reasons": resource_reasons + dep_reasons,
        "resource_reasons": resource_reasons,
        "missing_deps": deps_missing,
        "deps": dep_details(conn, session["code"]),
    }
