// src/main.jsx — updated with ModelRegistry page
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { LayoutDashboard, Search, MessageSquare, Database, Upload, GitBranch } from "lucide-react";

import "./index.css";
import RiskDashboard   from "./pages/RiskDashboard.jsx";
import CustomerProfile from "./pages/CustomerProfile.jsx";
import AICreditAnalyst from "./pages/AICreditAnalyst.jsx";
import BatchUpload     from "./pages/BatchUpload.jsx";
import ModelRegistry   from "./pages/ModelRegistry.jsx";

const NAV = [
  { to: "/",         icon: LayoutDashboard, label: "Portfolio"      },
  { to: "/customer", icon: Search,          label: "Customer"       },
  { to: "/analyst",  icon: MessageSquare,   label: "AI Analyst"     },
  { to: "/batch",    icon: Upload,          label: "Batch Score"    },
  { to: "/models",   icon: GitBranch,       label: "Model Registry" },
];

function Sidebar() {
  return (
    <aside style={{
      width:220, flexShrink:0, background:"var(--bg-surface)",
      borderRight:"1px solid var(--border)", display:"flex",
      flexDirection:"column", padding:"24px 0",
    }}>
      <div style={{ padding:"0 20px 28px" }}>
        <div style={{ display:"flex", alignItems:"center", gap:10,
                      color:"var(--teal)", fontWeight:600, fontSize:16 }}>
          <Database size={20} />
          <span>Risk<span style={{ color:"var(--text-primary)" }}>Lake</span></span>
        </div>
        <div style={{ fontSize:11, color:"var(--text-secondary)", marginTop:4 }}>
          Credit Risk Intelligence
        </div>
      </div>
      <nav style={{ flex:1 }}>
        {NAV.map(({ to, icon:Icon, label }) => (
          <NavLink key={to} to={to} end={to==="/"} style={({ isActive }) => ({
            display:"flex", alignItems:"center", gap:10,
            padding:"10px 20px", textDecoration:"none",
            color: isActive ? "var(--teal)" : "var(--text-secondary)",
            background: isActive ? "var(--teal-glow)" : "transparent",
            borderLeft: isActive ? "2px solid var(--teal)" : "2px solid transparent",
            fontSize:13, fontWeight: isActive ? 500 : 400, transition:"all .15s",
          })}>
            <Icon size={15} />{label}
          </NavLink>
        ))}
      </nav>
      <div style={{ padding:"0 20px", fontSize:11, color:"var(--text-muted)",
                    borderTop:"1px solid var(--border)", paddingTop:16 }}>
        <div>Bronze → Silver → Gold</div>
        <div style={{ marginTop:2 }}>Medallion Lakehouse</div>
      </div>
    </aside>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div style={{ display:"flex", height:"100vh", overflow:"hidden" }}>
        <Sidebar />
        <main style={{ flex:1, overflow:"auto", padding:"28px 32px" }}>
          <Routes>
            <Route path="/"        element={<RiskDashboard />}   />
            <Route path="/customer"element={<CustomerProfile />} />
            <Route path="/analyst" element={<AICreditAnalyst />} />
            <Route path="/batch"   element={<BatchUpload />}     />
            <Route path="/models"  element={<ModelRegistry />}   />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
