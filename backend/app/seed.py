from __future__ import annotations

from datetime import datetime, timezone

from app.db import connect, init_db


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_if_empty() -> None:
    init_db()
    conn = connect()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM rooms").fetchone()["c"]
        if n == 0:
            # rooms 表 = 算力槽；teachers 表 = 执行器（库表名兼容底座，界面/题面用语为数仓皮）
            rooms = [
                ("S-ETL-01", "ETL 主槽 A", 80),
                ("S-ETL-02", "ETL 主槽 B", 30),
                ("S-BI-01", "报表槽甲", 40),
                ("S-BI-02", "报表槽乙", 40),
            ]
            for code, name, cap in rooms:
                conn.execute(
                    "INSERT INTO rooms(code, name, capacity, active) VALUES(?,?,?,1)",
                    (code, name, cap),
                )
            teachers = [
                ("E-PIPE-01", "管道执行器甲", "ETL"),
                ("E-PIPE-02", "管道执行器乙", "ETL"),
                ("E-BI-01", "报表执行器甲", "BI"),
                ("E-BI-02", "报表执行器乙", "BI"),
            ]
            for code, name, subject in teachers:
                conn.execute(
                    "INSERT INTO teachers(code, name, subject, active) VALUES(?,?,?,1)",
                    (code, name, subject),
                )
            day = "2026-11-20"
            sessions = [
                ("W-DIM-01", "维表刷新窗", "ETL", "S-ETL-01", "E-PIPE-01", day, 9 * 60, 10 * 60 + 30),
                ("W-FACT-01", "事实入湖窗", "ETL", "S-ETL-02", "E-PIPE-02", day, 9 * 60, 10 * 60 + 30),
                ("W-RPT-01", "日报物化窗", "BI", "S-BI-01", "E-BI-01", day, 13 * 60, 14 * 60 + 30),
                ("W-RPT-02", "看板刷新窗", "BI", "S-BI-02", "E-BI-02", day, 13 * 60, 14 * 60 + 30),
            ]
            for row in sessions:
                conn.execute(
                    "INSERT INTO sessions(code, title, subject, room_code, teacher_code, day, start_min, end_min, status) "
                    "VALUES(?,?,?,?,?,?,?,?, 'draft')",
                    row,
                )
            conn.execute(
                "INSERT INTO watermarks(key, value, updated_at) VALUES('open_leases', 0, ?)",
                (_now(),),
            )
            conn.execute(
                "INSERT INTO watermarks(key, value, updated_at) VALUES('conflict_count', 0, ?)",
                (_now(),),
            )
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('conflict_mode', 'reject')",
            )
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('fixture_day', ?)",
                (day,),
            )
        # 依赖台账（独立于资源种子，老库也能补上）
        if conn.execute("SELECT COUNT(*) c FROM datasets").fetchone()["c"] == 0:
            datasets = [
                ("D-DIM-ORG", "组织维表", 1),
                ("D-DIM-USER", "用户维表", 1),
                ("D-ODS-ORDER", "订单 ODS", 0),  # 依赖未到数：演示缺依赖旁路
                ("D-ADS-DAILY", "日报 ADS", 1),
            ]
            for code, name, available in datasets:
                conn.execute(
                    "INSERT INTO datasets(code, name, available, updated_at) VALUES(?,?,?,?)",
                    (code, name, available, _now()),
                )
        # 批窗依赖声明（只挂到已存在的批窗上）
        if conn.execute("SELECT COUNT(*) c FROM session_deps").fetchone()["c"] == 0:
            deps = [
                ("W-DIM-01", "D-DIM-ORG"),
                ("W-DIM-01", "D-DIM-USER"),
                ("W-FACT-01", "D-ODS-ORDER"),
                ("W-FACT-01", "D-DIM-USER"),
                ("W-RPT-01", "D-ADS-DAILY"),
            ]
            for session_code, dataset_code in deps:
                exists = conn.execute(
                    "SELECT 1 FROM sessions WHERE code=?", (session_code,)
                ).fetchone()
                if exists:
                    conn.execute(
                        "INSERT OR IGNORE INTO session_deps(session_code, dataset_code) VALUES(?,?)",
                        (session_code, dataset_code),
                    )
        conn.commit()
    finally:
        conn.close()
