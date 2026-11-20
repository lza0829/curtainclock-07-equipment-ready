import { useEffect, useState } from "react";
import { api } from "../api";

function fmtMin(m) {
  const h = String(Math.floor(m / 60)).padStart(2, "0");
  const mm = String(m % 60).padStart(2, "0");
  return `${h}:${mm}`;
}

export default function Leases() {
  const [rows, setRows] = useState([]);
  const [bypassOnly, setBypassOnly] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function load(flag = bypassOnly) {
    setRows(await api.leases(flag));
  }

  useEffect(() => {
    load().catch((e) => setErr(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggleFilter(flag) {
    setBypassOnly(flag);
    setErr("");
    try {
      await load(flag);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function closeOne(lease_no) {
    setMsg("");
    setErr("");
    try {
      const r = await api.closeLease(lease_no);
      setMsg(
        `已关窗释放 ${r.lease_no}；在途租约 ${r.open_leases}` +
          (r.was_bypass ? `；旁路在途 ${r.bypass_inflight}` : "")
      );
      await load();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <section className="panel">
      <h2>租约</h2>
      <label className="filter">
        <input
          type="checkbox"
          checked={bypassOnly}
          onChange={(e) => toggleFilter(e.target.checked)}
        />
        仅看旁路租约（与总览「旁路在途」同源）
      </label>
      {msg && <div className="msg">{msg}</div>}
      {err && <div className="msg err">{err}</div>}
      <table>
        <thead>
          <tr>
            <th>租约号</th>
            <th>批窗</th>
            <th>资源</th>
            <th>时段</th>
            <th>旁路标记</th>
            <th>状态</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={7}>{bypassOnly ? "无旁路租约" : "暂无租约"}</td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.lease_no}>
              <td>{r.lease_no}</td>
              <td>{r.session_code}</td>
              <td>
                {r.room_code} / {r.teacher_code}
              </td>
              <td>
                {r.day} {fmtMin(r.start_min)}–{fmtMin(r.end_min)}
              </td>
              <td>
                {r.bypass ? (
                  <>
                    <span className="tag bypass">旁路</span>
                    <small className="hint">
                      缺：{(r.missing_deps || []).join("、")}
                    </small>
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td>{r.status === "open" ? "占用中" : "已释放"}</td>
              <td>
                <button
                  className="secondary"
                  disabled={r.status !== "open"}
                  onClick={() => closeOne(r.lease_no)}
                >
                  关窗释放
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
