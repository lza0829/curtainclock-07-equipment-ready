# -*- coding: utf-8 -*-
"""幕窗钟 0-1 冒烟：依赖台账 → 就绪 → 缺依赖旁路开窗 → 关窗互证。

全局架构（唯一）：缺依赖旁路占用 ——
  缺依赖不拒开窗，但必须同事务：落 open 租约 + 批窗/租约旁路标记（快照缺失依赖），
  旁路在途计数与标记过滤同源；算力槽/执行器硬冲突仍拒绝并写冲突水位。
  缺依赖却无旁路标记的静默开窗成功 = 非法。

核对项：
  1. 缺依赖 → 就绪判拒（ready=false 且列缺失依赖）
  2. 旁路臂成功必有标记且旁路计数 +1
  3. 总览旁路计数与标记过滤同源
  4. 硬冲突仍拒（409 + 冲突水位）
  5. 依赖恢复后新开窗无旁路
  6. 旁路窗关窗同时减占用与旁路计数
  7. 依赖变更与开窗并发不得假齐套、计数不漂移
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:11100/api"
DAY = "2026-11-20"


def call(method: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"detail": raw}
        return e.code, payload


def assert_marker_invariant(where: str) -> None:
    """无标记的静默成功非法：每条租约 bypass ⟺ 缺失依赖快照非空。"""
    st, rows = call("GET", "/leases")
    assert st == 200, rows
    for r in rows:
        assert r["bypass"] == (len(r["missing_deps"]) > 0), (
            f"{where}: 租约 {r['lease_no']} 标记与缺失依赖快照不一致: {r}"
        )


def main() -> None:
    run = str(int(time.time()))[-6:]

    # 清场：关掉可能残留的 open 租约，拿到干净基线
    st, rows = call("GET", "/leases")
    assert st == 200, rows
    for r in rows:
        if r["status"] == "open":
            call("POST", "/leases/close", {"lease_no": r["lease_no"]})
    st, dash0 = call("GET", "/dashboard")
    assert st == 200 and dash0["open_leases"] == 0 and dash0["bypass_inflight"] == 0, dash0
    print("baseline", dash0)

    # 台账：把 D-ODS-ORDER 置为不可用（缺依赖场景）
    st, r = call("POST", "/datasets/D-ODS-ORDER/availability", {"available": False})
    assert st == 200 and r["available"] is False, r
    st, dash = call("GET", "/dashboard")
    assert dash["datasets_unavailable"] >= 1, dash

    # 0) 种子批窗 W-FACT-01 的就绪联动（批窗页数据源）
    st, ready = call("GET", "/sessions/W-FACT-01/ready")
    assert st == 200 and ready["ready"] is False, ready
    assert ready["missing_deps"] == ["D-ODS-ORDER"], ready
    print("seed_window_ready_denied", ready["reasons"])

    # 1) 声明依赖的批窗：缺依赖 → 就绪判拒
    code_a = f"W-SMK-A-{run}"
    st, created = call("POST", "/sessions", {
        "code": code_a, "title": "冒烟·缺依赖窗", "subject": "ETL",
        "room_code": "S-ETL-01", "teacher_code": "E-PIPE-01",
        "day": DAY, "start_min": 18 * 60, "end_min": 19 * 60,
        "deps": ["D-ODS-ORDER", "D-DIM-USER"],
    })
    assert st == 200, created
    st, ready = call("GET", f"/sessions/{code_a}/ready")
    assert st == 200 and ready["ready"] is False, ready
    assert ready["missing_deps"] == ["D-ODS-ORDER"], ready
    assert ready["resource_reasons"] == [], ready
    print("1_ready_denied", ready["reasons"])

    # 2) 旁路臂：缺依赖开窗成功，必有标记且旁路计数 +1
    st, opened = call("POST", "/leases/open", {"session_code": code_a})
    assert st == 200, opened
    assert opened["bypass"] is True, opened
    assert opened["missing_deps"] == ["D-ODS-ORDER"], opened
    assert opened["bypass_inflight"] == 1, opened
    st, dash = call("GET", "/dashboard")
    assert dash["bypass_inflight"] == 1 and dash["open_leases"] == 1, dash
    print("2_bypass_open", opened)

    # 3) 总览旁路计数与标记过滤同源
    st, marked = call("GET", "/leases?bypass=1")
    assert st == 200, marked
    open_marked = [x for x in marked if x["status"] == "open"]
    assert len(open_marked) == dash["bypass_inflight"] == 1, (marked, dash)
    assert open_marked[0]["lease_no"] == opened["lease_no"], open_marked
    assert open_marked[0]["missing_deps"] == ["D-ODS-ORDER"], open_marked
    assert_marker_invariant("bypass_open")
    print("3_same_source_ok", {"bypass_inflight": dash["bypass_inflight"], "open_marked": len(open_marked)})

    # 4) 硬冲突仍拒：同算力槽同时段 → 409 + 冲突水位，不落租约
    code_dup = f"W-SMK-DUP-{run}"
    st, r = call("POST", "/sessions", {
        "code": code_dup, "title": "冒烟·硬冲突窗", "subject": "ETL",
        "room_code": "S-ETL-01", "teacher_code": "E-PIPE-02",
        "day": DAY, "start_min": 18 * 60 + 30, "end_min": 19 * 60,
        "deps": [],
    })
    assert st == 200, r
    st, conflict = call("POST", "/leases/open", {"session_code": code_dup})
    assert st == 409, conflict
    st, dash = call("GET", "/dashboard")
    assert dash["conflict_count"] >= 1 and dash["open_leases"] == 1, dash
    print("4_hard_conflict_rejected", conflict)

    # 5) 依赖恢复 → 新开窗无旁路
    st, r = call("POST", "/datasets/D-ODS-ORDER/availability", {"available": True})
    assert st == 200 and r["available"] is True, r
    code_b = f"W-SMK-B-{run}"
    st, r = call("POST", "/sessions", {
        "code": code_b, "title": "冒烟·恢复后齐套窗", "subject": "ETL",
        "room_code": "S-ETL-01", "teacher_code": "E-PIPE-01",
        "day": DAY, "start_min": 19 * 60, "end_min": 20 * 60,
        "deps": ["D-ODS-ORDER"],
    })
    assert st == 200, r
    st, ready = call("GET", f"/sessions/{code_b}/ready")
    assert st == 200 and ready["ready"] is True, ready
    st, opened_b = call("POST", "/leases/open", {"session_code": code_b})
    assert st == 200, opened_b
    assert opened_b["bypass"] is False and opened_b["missing_deps"] == [], opened_b
    st, dash = call("GET", "/dashboard")
    assert dash["bypass_inflight"] == 1 and dash["open_leases"] == 2, dash
    print("5_clean_open_after_recover", opened_b)

    # 6) 旁路窗关窗：占用与旁路计数同事务同减
    st, closed = call("POST", "/leases/close", {"lease_no": opened["lease_no"]})
    assert st == 200, closed
    assert closed["was_bypass"] is True, closed
    assert closed["open_leases"] == 1 and closed["bypass_inflight"] == 0, closed
    st, dash = call("GET", "/dashboard")
    assert dash["open_leases"] == 1 and dash["bypass_inflight"] == 0, dash
    print("6_bypass_closed", closed)
    st, closed_b = call("POST", "/leases/close", {"lease_no": opened_b["lease_no"]})
    assert st == 200 and closed_b["open_leases"] == 0, closed_b

    # 7) 并发：依赖变更与开窗交织 —— 不得假齐套、计数与标记不漂移
    st, ds = call("GET", "/datasets")
    assert st == 200, ds
    if not any(d["code"] == "D-TOGGLE" for d in ds):
        st, r = call("POST", "/datasets", {"code": "D-TOGGLE", "name": "并发拨动依赖"})
        assert st in (200, 201), r
    rooms = ["S-ETL-01", "S-ETL-02", "S-BI-01", "S-BI-02"]
    teachers = ["E-PIPE-01", "E-PIPE-02", "E-BI-01", "E-BI-02"]
    codes = []
    for i in range(8):
        c = f"W-SMK-C{run}-{i}"
        st, r = call("POST", "/sessions", {
            "code": c, "title": f"冒烟·并发窗{i}", "subject": "ETL",
            "room_code": rooms[i % 4], "teacher_code": teachers[i % 4],
            "day": DAY,
            "start_min": 20 * 60 + (i // 4) * 30,
            "end_min": 20 * 60 + (i // 4) * 30 + 25,
            "deps": ["D-TOGGLE"],
        })
        assert st == 200, r
        codes.append(c)

    stop = False

    def toggler() -> None:
        val = False
        while not stop:
            call("POST", "/datasets/D-TOGGLE/availability", {"available": val})
            val = not val
            time.sleep(0.01)

    results: list[tuple[int, dict]] = []

    def opener(c: str) -> None:
        results.append(call("POST", "/leases/open", {"session_code": c}))

    t = threading.Thread(target=toggler)
    t.start()
    threads = [threading.Thread(target=opener, args=(c,)) for c in codes]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    stop = True
    t.join()

    for st, r in results:
        assert st == 200, r  # 无论齐套与否，开窗路径不得崩
        assert r["bypass"] == (len(r["missing_deps"]) > 0), r
    bypass_opens = sum(1 for _, r in results if r["bypass"])
    st, dash = call("GET", "/dashboard")
    st, marked = call("GET", "/leases?bypass=1")
    open_marked = [x for x in marked if x["status"] == "open"]
    assert dash["bypass_inflight"] == len(open_marked) == bypass_opens, (
        dash, len(open_marked), bypass_opens,
    )
    assert dash["open_leases"] == 8, dash
    assert_marker_invariant("concurrent")
    print("7_concurrent_ok", {"opens": 8, "bypass_opens": bypass_opens})

    # 收尾：并发窗全部关窗，计数回落
    for st, r in results:
        st2, closed = call("POST", "/leases/close", {"lease_no": r["lease_no"]})
        assert st2 == 200, closed
    st, dash = call("GET", "/dashboard")
    assert dash["open_leases"] == 0 and dash["bypass_inflight"] == 0, dash
    assert_marker_invariant("final")

    # 台账复位到种子叙事（D-ODS-ORDER 未到数）
    call("POST", "/datasets/D-ODS-ORDER/availability", {"available": False})
    call("POST", "/datasets/D-TOGGLE/availability", {"available": True})
    print("final", dash)
    print("SMOKE_OK")


if __name__ == "__main__":
    main()
