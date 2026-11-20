from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import connect, transaction
from app.services.ready import readiness

router = APIRouter(tags=["sessions"])


class SessionIn(BaseModel):
    code: str = Field(min_length=2)
    title: str
    subject: str
    room_code: str
    teacher_code: str
    day: str
    start_min: int
    end_min: int
    deps: list[str] = Field(default_factory=list)


class DepsIn(BaseModel):
    deps: list[str] = Field(default_factory=list)


def _clean_deps(deps: list[str]) -> list[str]:
    return [d for d in dict.fromkeys(x.strip() for x in deps) if d]


def _insert_deps(conn, session_code: str, deps: list[str]) -> None:
    for dep in _clean_deps(deps):
        conn.execute(
            "INSERT INTO session_deps(session_code, dataset_code) VALUES(?,?)",
            (session_code, dep),
        )


@router.get("/sessions")
def list_sessions():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY day, start_min, code"
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["bypass"] = bool(item["bypass"])
            item["readiness"] = readiness(conn, r)
            out.append(item)
        return out
    finally:
        conn.close()


@router.post("/sessions")
def create_session(body: SessionIn):
    if body.end_min <= body.start_min:
        raise HTTPException(400, "结束时刻必须晚于开始时刻")
    try:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO sessions(code, title, subject, room_code, teacher_code, day, start_min, end_min, status) "
                "VALUES(?,?,?,?,?,?,?,?, 'draft')",
                (
                    body.code,
                    body.title,
                    body.subject,
                    body.room_code,
                    body.teacher_code,
                    body.day,
                    body.start_min,
                    body.end_min,
                ),
            )
            _insert_deps(conn, body.code, body.deps)
            row = conn.execute(
                "SELECT * FROM sessions WHERE code=?", (body.code,)
            ).fetchone()
            item = dict(row)
            item["bypass"] = bool(item["bypass"])
            return {**item, "readiness": readiness(conn, row)}
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.put("/sessions/{code}/deps")
def set_session_deps(code: str, body: DepsIn):
    """改批窗依赖声明（仅待开窗）。与开窗同属事务串行，

    声明变更不会被开窗读成假齐套。
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE code=?", (code,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "批窗不存在")
        if row["status"] != "draft":
            raise HTTPException(409, "仅待开窗批窗可改依赖声明")
        conn.execute(
            "DELETE FROM session_deps WHERE session_code=?", (code,)
        )
        _insert_deps(conn, code, body.deps)
        row = conn.execute(
            "SELECT * FROM sessions WHERE code=?", (code,)
        ).fetchone()
        return {"code": code, "readiness": readiness(conn, row)}


@router.get("/sessions/{code}/ready")
def session_ready(code: str):
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE code=?", (code,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "批窗不存在")
        return readiness(conn, row)
    finally:
        conn.close()
