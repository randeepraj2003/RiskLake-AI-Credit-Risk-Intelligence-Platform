// src/pages/RiskDashboard.jsx
// Portfolio-level risk overview — KPI cards, grade distribution bar,
// 30-day PD trend sparkline.
// Data from: GET /api/risk/portfolio

import { useState, useEffect } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { TrendingUp, AlertTriangle, Users, Activity } from "lucide-react";
import { getPortfolio } from "../api/client.js";

// ── Helpers ───────────────────────────────────────────────────────────────────

const GRADE_COLOR = { A:"#3fb950", B:"#58a6ff", C:"#e3b341", D:"#f78166", E:"#ff7b72" };
const fmt = (n) => n == null ? "—" : (n * 100).toFixed(1) + "%";
const fmtINR = (n) => n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN");

function KpiCard({ icon: Icon, label, value, sub, accent }) {
  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border)",
      borderRadius: "var(--r-lg)", padding: "20px 24px",
      display: "flex", flexDirection: "column", gap: 8,
      borderTop: `3px solid ${accent}`,
    }}>
      <div style={{ display:"flex", alignItems:"center", gap:8, color:"var(--text-secondary)", fontSize:12 }}>
        <Icon size={14} /> {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 600, fontFamily: "var(--font-mono)", color:"var(--text-primary)" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{sub}</div>}
    </div>
  );
}

function GradeBar({ data }) {
  const total = data.reduce((s, d) => s + (d.count || 0), 0);
  return (
    <div>
      <div style={{ display:"flex", gap:2, borderRadius:6, overflow:"hidden", height:14, marginBottom:10 }}>
        {data.map(d => (
          <div key={d.risk_grade} style={{
            flex: d.count / total, background: GRADE_COLOR[d.risk_grade] || "#444",
            transition: "flex .4s ease",
          }} title={`Grade ${d.risk_grade}: ${d.count} applications`} />
        ))}
      </div>
      <div style={{ display:"flex", gap:16, flexWrap:"wrap" }}>
        {data.map(d => (
          <div key={d.risk_grade} style={{ display:"flex", alignItems:"center", gap:6, fontSize:12 }}>
            <span style={{ width:10, height:10, borderRadius:2, background: GRADE_COLOR[d.risk_grade], display:"inline-block" }} />
            <span style={{ color:"var(--text-secondary)" }}>Grade {d.risk_grade}</span>
            <span className="mono" style={{ color:"var(--text-primary)" }}>{d.count}</span>
            <span style={{ color:"var(--text-muted)" }}>({fmt(d.avg_pd)} avg PD)</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background:"var(--bg-card)", border:"1px solid var(--border)",
      borderRadius:"var(--r-md)", padding:"10px 14px", fontSize:12,
    }}>
      <div style={{ color:"var(--text-secondary)", marginBottom:4 }}>{label}</div>
      <div className="mono" style={{ color:"var(--teal)" }}>
        Avg PD: {fmt(payload[0]?.value)}
      </div>
      <div style={{ color:"var(--text-secondary)" }}>
        {payload[0]?.payload?.scored_count} scored
      </div>
    </div>
  );
};

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RiskDashboard() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    getPortfolio()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:16 }}>
      {[...Array(4)].map((_, i) => (
        <div key={i} className="skeleton" style={{ height:110, borderRadius:"var(--r-lg)" }} />
      ))}
    </div>
  );

  if (error) return (
    <div style={{
      background:"var(--bg-card)", border:"1px solid var(--grade-e)",
      borderRadius:"var(--r-lg)", padding:24, color:"var(--grade-e)",
      display:"flex", gap:10, alignItems:"center",
    }}>
      <AlertTriangle size={18} />
      <div>
        <div style={{ fontWeight:500 }}>Failed to load portfolio</div>
        <div style={{ fontSize:12, marginTop:4, color:"var(--text-secondary)" }}>{error}</div>
        <div style={{ fontSize:12, marginTop:4, color:"var(--text-muted)" }}>
          Make sure the FastAPI server is running: <span className="mono">uvicorn api.main:app --reload</span>
        </div>
      </div>
    </div>
  );

  const grades    = data?.grade_distribution || [];
  const trend     = (data?.pd_trend_30d || []).map(d => ({
    ...d,
    date: d.date?.slice(5),   // show MM-DD only
  }));
  const highRisk  = data?.high_risk_count || 0;
  const total     = data?.total_applications || 0;
  const avgPd     = data?.portfolio_avg_pd || 0;

  return (
    <div className="fade-in">
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>Portfolio Risk Overview</h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 4 }}>
          Medallion lakehouse · Bronze → Silver → Gold · Powered by Random Forest + SHAP
        </p>
      </div>

      {/* KPI cards */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:16, marginBottom:28 }}>
        <KpiCard icon={Users}      label="Total Applications" value={total.toLocaleString()}  accent="var(--teal)"    sub="All scored applications" />
        <KpiCard icon={Activity}   label="Portfolio Avg PD"   value={fmt(avgPd)}               accent="var(--grade-b)" sub="Ensemble model (RF 70% + LR 30%)" />
        <KpiCard icon={AlertTriangle} label="High-Risk (D+E)" value={highRisk.toLocaleString()} accent="var(--grade-d)" sub={`${data?.high_risk_pct?.toFixed(1)}% of portfolio`} />
        <KpiCard icon={TrendingUp} label="Grade A (Safe)"     value={grades.find(g=>g.risk_grade==="A")?.count || 0}
                 accent="var(--grade-a)" sub="PD < 5%" />
      </div>

      {/* Two-column section */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:20, marginBottom:20 }}>

        {/* Grade distribution */}
        <div style={{
          background:"var(--bg-card)", border:"1px solid var(--border)",
          borderRadius:"var(--r-lg)", padding:24,
        }}>
          <h2 style={{ fontSize:14, fontWeight:500, marginBottom:16 }}>Grade Distribution</h2>
          {grades.length > 0 ? (
            <>
              <GradeBar data={grades} />
              <div style={{ marginTop:20, height:160 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={grades} barSize={32}>
                    <XAxis dataKey="risk_grade" tick={{ fontSize:12, fill:"var(--text-secondary)" }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize:11, fill:"var(--text-secondary)" }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background:"var(--bg-card)", border:"1px solid var(--border)", borderRadius:8, fontSize:12 }}
                      cursor={{ fill:"rgba(255,255,255,.04)" }}
                    />
                    <Bar dataKey="count" radius={[4,4,0,0]}>
                      {grades.map(g => <Cell key={g.risk_grade} fill={GRADE_COLOR[g.risk_grade] || "#444"} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <div style={{ color:"var(--text-secondary)", fontSize:13 }}>No grade data yet.</div>
          )}
        </div>

        {/* 30-day PD trend */}
        <div style={{
          background:"var(--bg-card)", border:"1px solid var(--border)",
          borderRadius:"var(--r-lg)", padding:24,
        }}>
          <h2 style={{ fontSize:14, fontWeight:500, marginBottom:4 }}>30-Day PD Trend</h2>
          <p style={{ fontSize:12, color:"var(--text-secondary)", marginBottom:16 }}>
            Daily average probability of default across all scored applications
          </p>
          {trend.length > 0 ? (
            <div style={{ height:200 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend}>
                  <defs>
                    <linearGradient id="pdGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="var(--teal)" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="var(--teal)" stopOpacity={0}   />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fontSize:10, fill:"var(--text-secondary)" }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tickFormatter={v => (v*100).toFixed(0)+"%" } tick={{ fontSize:10, fill:"var(--text-secondary)" }} axisLine={false} tickLine={false} width={42} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="avg_pd" stroke="var(--teal)" strokeWidth={2} fill="url(#pdGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div style={{ color:"var(--text-secondary)", fontSize:13 }}>
              No trend data yet. Run the Airflow pipeline first.
            </div>
          )}
        </div>

      </div>

      {/* Grade reference table */}
      <div style={{
        background:"var(--bg-card)", border:"1px solid var(--border)",
        borderRadius:"var(--r-lg)", padding:24,
      }}>
        <h2 style={{ fontSize:14, fontWeight:500, marginBottom:16 }}>Grade Reference — Basel II Aligned</h2>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
          <thead>
            <tr style={{ color:"var(--text-secondary)", textAlign:"left" }}>
              {["Grade","PD Range","Risk Level","Action"].map(h => (
                <th key={h} style={{ padding:"6px 12px", borderBottom:"1px solid var(--border)", fontWeight:500 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              ["A","< 5%",   "Minimal",   "Approve — standard terms"],
              ["B","5–15%",  "Low",       "Approve — risk-adjusted pricing"],
              ["C","15–30%", "Moderate",  "Enhanced monitoring required"],
              ["D","30–50%", "High",      "Senior credit officer review"],
              ["E","> 50%",  "Very High", "Decline recommended"],
            ].map(([g, pd, risk, action]) => (
              <tr key={g} style={{ borderBottom:"1px solid var(--border-light)" }}>
                <td style={{ padding:"10px 12px" }}>
                  <span className={`grade-${g.toLowerCase()}`} style={{ fontWeight:600, fontFamily:"var(--font-mono)" }}>
                    Grade {g}
                  </span>
                </td>
                <td className="mono" style={{ padding:"10px 12px", color:"var(--text-secondary)" }}>{pd}</td>
                <td style={{ padding:"10px 12px", color:"var(--text-secondary)" }}>{risk}</td>
                <td style={{ padding:"10px 12px", color:"var(--text-secondary)" }}>{action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
