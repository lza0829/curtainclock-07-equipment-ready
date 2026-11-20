from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import connect, transaction

router = APIRouter(tags=["datasets"])


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DatasetIn(BaseModel):
    code: str = Field(min_length=2)
    name: str = Field(min_length=1)


class AvailabilityIn(BaseModel):
    available: bool


@router.get("/datasets")
def list_datasets():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM datasets ORDER BY code"
        ).fetchall()
        deps = conn.execute(
            "SELECT dataset_code, session_code FROM session_deps "
            "ORDER BY dataset_code, session_code"
        ).fetchall()
        used_by: dict[str, list[str]] = {}
        for d in deps:
            used_by.setdefault(d["dataset_code"], []).append(d["session_code"])
        return [
            {
                "code": r["code"],
                "name": r["name"],
                "available": bool(r["available"]),
                "updated_at": r["updated_at"],
                "declared_by": used_by.get(r["code"], []),
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.post("/datasets", status_code=201)
def create_dataset(body: DatasetIn):
    try:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO datasets(code, name, available, updated_at) "
                "VALUES(?,?,1,?)",
                (body.code, body.name, _now()),
            )
            row = conn.execute(
                "SELECT * FROM datasets WHERE code=?", (body.code,)
            ).fetchone()
            return {
                "code": row["code"],
                "name": row["name"],
                "available": True,
                "updated_at": row["updated_at"],
            }
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.post("/datasets/{code}/availability")
def set_availability(code: str, body: AvailabilityIn):
    """台账可用性变更。与开窗同事务串行（BEGIN IMMEDIATE），

    开窗读到的齐套判定不会是过期快照（不得假齐套）。
    """
    with transaction() as conn:
        row = conn.execute(
            "SELECT id FROM datasets WHERE code=?", (code,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"依赖数据集不存在：{code}")
        conn.execute(
            "UPDATE datasets SET available=?, updated_at=? WHERE code=?",
            (1 if body.available else 0, _now(), code),
        )
    return {"code": code, "available": body.available}
