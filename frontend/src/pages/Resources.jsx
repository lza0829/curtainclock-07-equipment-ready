import { useEffect, useState } from "react";
import { api } from "../api";

export default function Resources() {
  const [rooms, setRooms] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function load() {
    const [r, t, d] = await Promise.all([
      api.rooms(),
      api.teachers(),
      api.datasets(),
    ]);
    setRooms(r);
    setTeachers(t);
    setDatasets(d);
  }

  useEffect(() => {
    load().catch((e) => setErr(e.message));
  }, []);

  async function toggleDataset(code, available) {
    setMsg("");
    setErr("");
    try {
      await api.setDatasetAvailability(code, available);
      setMsg(
        `依赖 ${code} 已${available ? "恢复可用" : "标记不可用"}；就绪判定与开窗旁路即刻联动`
      );
      setDatasets(await api.datasets());
    } catch (e) {
      setErr(e.message);
    }
  }

  if (err && !rooms.length && !datasets.length)
    return <div className="msg err">{err}</div>;

  return (
    <>
      <section className="panel">
        <h2>依赖数据集台账</h2>
        {msg && <div className="msg">{msg}</div>}
        {err && <div className="msg err">{err}</div>}
        <table>
          <thead>
            <tr>
              <th>编码</th>
              <th>名称</th>
              <th>状态</th>
              <th>声明批窗</th>
              <th>变更时间</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((d) => (
              <tr key={d.code}>
                <td>{d.code}</td>
                <td>{d.name}</td>
                <td>
                  {d.available ? (
                    <span className="tag live">可用</span>
                  ) : (
                    <span className="tag bad">不可用</span>
                  )}
                </td>
                <td>
                  {d.declared_by.length ? d.declared_by.join("、") : "—"}
                </td>
                <td>{d.updated_at}</td>
                <td>
                  <button
                    className="secondary"
                    onClick={() => toggleDataset(d.code, !d.available)}
                  >
                    {d.available ? "标记不可用" : "恢复可用"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h2>算力槽</h2>
        <table>
          <thead>
            <tr>
              <th>编码</th>
              <th>名称</th>
              <th>容量</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {rooms.map((r) => (
              <tr key={r.code}>
                <td>{r.code}</td>
                <td>{r.name}</td>
                <td>{r.capacity}</td>
                <td>{r.active ? "启用" : "停用"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h2>执行器</h2>
        <table>
          <thead>
            <tr>
              <th>编码</th>
              <th>姓名</th>
              <th>作业类型</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {teachers.map((t) => (
              <tr key={t.code}>
                <td>{t.code}</td>
                <td>{t.name}</td>
                <td>{t.subject}</td>
                <td>{t.active ? "启用" : "停用"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
