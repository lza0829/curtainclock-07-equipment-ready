import { useEffect, useState } from "react";
import { api } from "../api";

export default function Home() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .dashboard()
      .then(setD)
      .catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="msg err">{err}</div>;
  if (!d) return <div className="panel">加载中…</div>;

  return (
    <section className="panel">
      <h2>今日水位 · {d.fixture_day}</h2>
      <div className="stats">
        <div className="stat">
          在途租约
          <b>{d.open_leases}</b>
        </div>
        <div className="stat">
          旁路在途
          <b>{d.bypass_inflight}</b>
        </div>
        <div className="stat">
          冲突计数
          <b>{d.conflict_count}</b>
        </div>
        <div className="stat">
          依赖不可用
          <b>{d.datasets_unavailable}</b>
        </div>
        <div className="stat">
          上课中
          <b>{d.live_sessions}</b>
        </div>
        <div className="stat">
          待开窗
          <b>{d.draft_sessions}</b>
        </div>
      </div>
      <p className="hint">
        旁路在途 = open 且带旁路标记的租约数，与「租约页 · 仅看旁路」过滤同源；
        缺依赖开窗必落旁路标记并计入旁路在途，关窗同时减占用与旁路计数。
      </p>
    </section>
  );
}
