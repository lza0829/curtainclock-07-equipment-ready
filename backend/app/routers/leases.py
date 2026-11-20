from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import connect, transaction
from app.services import lease as lease_svc

router = APIRouter(tags=["leases"])


class OpenBody(BaseModel):
    session_code: str


class CloseBody(BaseModel):
    lease_no: str


def _lease_out(row) -> dict:
    item = dict(row)
    item["bypass"] = bool(item["bypass"])
    try:
        item["missing_deps"] = json.loads(item.get("missing_deps") or "[]")
    except (TypeError, ValueError):
        item["missing_deps"] = []
    return item


@router.get("/leases")
def list_leases(bypass: int | None = None):
    """租约快照。bypass=1 过滤即「旁路标记过滤」，

    与总览旁路在途计数同源（同一张 leases 表同一谓词）。
    """
    conn = connect()
    try:
        sql = "SELECT * FROM leases"
        args: tuple = ()
        if bypass is not None:
            sql += " WHERE bypass=?"
            args = (1 if bypass else 0,)
        rows = conn.execute(sql + " ORDER BY id DESC", args).fetchall()
        return [_lease_out(r) for r in rows]
    finally:
        conn.close()


@router.get("/conflicts")
def list_conflicts():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM conflicts ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/leases/open")
def open_lease(body: OpenBody):
    try:
        with transaction() as conn:
            result = lease_svc.open_lease(conn, body.session_code)
        if result.get("ok") is False:
            raise HTTPException(409, result.get("error") or "开窗冲突")
        return result
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/leases/close")
def close_lease(body: CloseBody):
    try:
        with transaction() as conn:
            return lease_svc.close_lease(conn, body.lease_no)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
