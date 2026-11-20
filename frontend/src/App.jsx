import { NavLink, Route, Routes } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Sessions from "./pages/Sessions.jsx";
import Resources from "./pages/Resources.jsx";
import Leases from "./pages/Leases.jsx";
import Conflicts from "./pages/Conflicts.jsx";

export default function App() {
  return (
    <div className="shell">
      <header className="hero">
        <h1 className="brand">幕窗钟</h1>
        <p>
          批窗声明上游依赖数据集：缺依赖开窗走旁路并同事务落标记租约，旁路在途与标记过滤同源；关窗同时减占用与旁路计数，冲突写入水位，数字同源可核。
        </p>
      </header>

      <nav className="nav">
        <NavLink to="/" end>
          总览
        </NavLink>
        <NavLink to="/sessions">批窗</NavLink>
        <NavLink to="/resources">资源与台账</NavLink>
        <NavLink to="/leases">租约</NavLink>
        <NavLink to="/conflicts">冲突</NavLink>
      </nav>

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/resources" element={<Resources />} />
        <Route path="/leases" element={<Leases />} />
        <Route path="/conflicts" element={<Conflicts />} />
      </Routes>
    </div>
  );
}
