# Curtainclock（幕窗钟）

骨架：**批窗定义 → 声明上游依赖数据集 → 算力槽/执行器/依赖就绪判定 → 开窗租约占用（缺依赖走旁路并落标记）→ 关窗释放与冲突/旁路水位互证**

- 前端：http://127.0.0.1:6100 （React + Vite）
- API：http://127.0.0.1:11100

## 架构决策（全局唯一）：缺依赖旁路占用

批窗声明的上游依赖数据集（`session_deps`）以依赖台账（`datasets`）可用性为准。
缺依赖时占用如何落、如何互证，全局只贯彻一种口径：

- **缺依赖不拒开窗**，但必须在**同一事务**里：落 `open` 租约、批窗与租约同打
  旁路标记（`bypass=1`）并快照缺失依赖（`leases.missing_deps`）、旁路在途计数随标记租约 +1。
- **旁路在途计数与标记过滤同源**：不另设水位，总览「旁路在途」就是
  `leases WHERE status='open' AND bypass=1` 的计数，与租约页「仅看旁路」过滤同一谓词，结构上不会漂移。
- **无标记的成功一律非法**：每条租约恒满足 `bypass=1 ⟺ 缺失依赖快照非空`（冒烟逐步断言）。
- **硬冲突仍拒**：算力槽/执行器停用或被占 → 开窗 409、写冲突水位、不落租约（底座 reject 口径不变）。
- **依赖变更与开窗并发不得假齐套**：就绪判定与开窗落租约同在 `BEGIN IMMEDIATE`
  事务内读台账；台账变更（`POST /datasets/{code}/availability`）与依赖声明变更
  （`PUT /sessions/{code}/deps`，仅待开窗）同事务串行，开窗读不到过期快照。
- **关窗互证**：旁路窗关窗同事务 `open_leases` −1 且租约离开 open 态，旁路在途同步 −1。

## 联动面

| 面 | 位置 |
| --- | --- |
| 依赖台账 | `GET/POST /datasets`、`POST /datasets/{code}/availability`；前端「资源与台账」页 |
| 批窗依赖声明 | 建窗 `deps` 字段、`PUT /sessions/{code}/deps`；批窗页依赖列（缺依赖红标） |
| 就绪 | `GET /sessions/{code}/ready`：`resource_reasons`（硬冲突）与 `missing_deps`（旁路臂）分列 |
| 开窗 | `POST /leases/open`：齐套正常开 / 缺依赖旁路开 / 硬冲突 409 |
| 租约快照 | `leases.bypass` + `leases.missing_deps`（开窗时刻缺失依赖快照） |
| 冲突 | `conflicts` 表 + `conflict_count` 水位（仅硬冲突） |
| 旁路计数 | 总览 `bypass_inflight`（open 且 bypass=1 派生）、`bypass_total`（历史累计） |
| 总览 | `GET /dashboard`：在途租约、旁路在途、冲突计数、依赖不可用等 |
| 批窗页/租约页 | 依赖芯片、旁路标记、「仅看旁路」过滤（与总览同源） |

## 本地冒烟（推荐）

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend && PYTHONPATH=$PWD/../backend ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 11100
# 另起终端
cd frontend && npm install && npm run dev   # 前端需 Node ≥18
# 冒烟（API 需在 11100 监听）
.venv/bin/python -I _smoke_api.py
```

浏览器打开 http://127.0.0.1:6100 ：资源与台账页把「订单 ODS」标记不可用 →
批窗页对缺依赖窗开窗（落旁路标记）→ 租约页「仅看旁路」与总览旁路在途对账 →
恢复依赖后新窗无旁路 → 关窗释放，占用与旁路计数同减。

冒烟核对（`_smoke_api.py`，可重复运行）：缺依赖就绪判拒 → 旁路臂成功必有标记且
旁路计数 +1 → 总览旁路计数与标记过滤同源 → 硬冲突仍拒 → 依赖恢复后新开窗无旁路 →
旁路窗关窗同时减占用与旁路计数 → 依赖变更与开窗并发（8 窗 + 台账拨动）不得假齐套、
计数不漂移 → 全程断言无「缺依赖却无旁路标记」的静默成功。

## Docker

```powershell
docker compose up -d --build
```
