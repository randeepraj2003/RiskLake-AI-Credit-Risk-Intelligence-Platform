// src/pages/CustomerProfile.jsx
// Look up a loan application by ID.
// Shows: PD score + risk grade badge + SHAP horizontal bar chart + customer fields
//        + decision badge (approve/refer/decline) + model comparison panel.
// Data from: GET /api/risk/predict/{id}  +  GET /api/risk/explain/{id}  +  GET /api/risk/decide/{id}

import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from "recharts";
import { Search, TrendingUp, TrendingDown, AlertCircle, CheckCircle } from "lucide-react";
import { getPrediction, getExplanation, getDecision } from "../api/client.js";

// ── Helpers ───────────────────────────────────────────────────────────────────

const GRADE_COLOR = { A:"#3fb950", B:"#58a6ff", C:"#e3b341", D:"#f78166", E:"#ff7b72" };
const fmt  = n => n == null ? "—" : (n * 100).toFixed(2) + "%";
const fmtN = n => n == null ? "—" : Number(n).toLocaleString("en-IN");
const fmtF = (n, d=4) => n == null ? "—" : Number(n).toFixed(d);

function GradeBadge({ grade }) {
  const color = GRADE_COLOR[grade] || "#888";
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap:6,
      background: color + "22", color, border:`1px solid ${color}55`,
      borderRadius:6, padding:"4px 12px", fontFamily:"var(--font-mono)",
      fontWeight:600, fontSize:16,
    }}>
      Grade {grade}
    </span>
  );
}

function PdGauge({ value }) {
  const pct = Math.min(100, (value || 0) * 100);
  const color = pct < 15 ? "var(--grade-a)" : pct < 30 ? "var(--grade-c)" : pct < 50 ? "var(--grade-d)" : "var(--grade-e)";
  return (
    <div>
      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6, fontSize:12, color:"var(--text-secondary)" }}>
        <span>PD Probability</span>
        <span className="mono" style={{ color, fontWeight:600 }}>{fmt(value)}</span>
      </div>
      <div style={{ height:8, background:"var(--bg-hover)", borderRadius:4, overflow:"hidden" }}>
        <div style={{
          width:`${pct}%`, height:"100%", background:color,
          borderRadius:4, transition:"width .6s ease",
        }} />
      </div>
      <div style={{ display:"flex", justifyContent:"space-between", marginTop:4, fontSize:10, color:"var(--text-muted)" }}>
        <span>0%</span><span>50%</span><span>100%</span>
      </div>
    </div>
  );
}

const ShapTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div style={{
      background:"var(--bg-card)", border:"1px solid var(--border)",
      borderRadius:"var(--r-md)", padding:"10px 14px", fontSize:12, maxWidth:280,
    }}>
      <div style={{ fontWeight:500, marginBottom:4, color:"var(--text-primary)" }}>{d?.feature}</div>
      <div className="mono" style={{ color: d?.shap_value > 0 ? "var(--grade-d)" : "var(--grade-a)", marginBottom:4 }}>
        SHAP: {d?.shap_value > 0 ? "+" : ""}{fmtF(d?.shap_value)}
      </div>
      <div style={{ color:"var(--text-secondary)", lineHeight:1.5 }}>{d?.label}</div>
    </div>
  );
};

function ShapChart({ drivers }) {
  if (!drivers?.length) return <div style={{ color:"var(--text-secondary)", fontSize:13 }}>No SHAP data available.</div>;

  const top = [...drivers].sort((a,b) => Math.abs(b.shap_value) - Math.abs(a.shap_value)).slice(0, 12);
  const data = top.map(d => ({
    ...d,
    feature: d.feature.replace(/_/g," "),
    abs: Math.abs(d.shap_value),
  }));

  return (
    <div>
      <div style={{ marginBottom:12, display:"flex", gap:16, fontSize:12 }}>
        <span style={{ display:"flex", alignItems:"center", gap:6 }}>
          <span style={{ width:10, height:10, background:"var(--grade-d)", borderRadius:2, display:"inline-block" }} />
          <span style={{ color:"var(--text-secondary)" }}>Increases risk</span>
        </span>
        <span style={{ display:"flex", alignItems:"center", gap:6 }}>
          <span style={{ width:10, height:10, background:"var(--grade-a)", borderRadius:2, display:"inline-block" }} />
          <span style={{ color:"var(--text-secondary)" }}>Reduces risk</span>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={data.length * 36 + 20}>
        <BarChart data={data} layout="vertical" margin={{ left:0, right:20, top:0, bottom:0 }}>
          <XAxis type="number" tick={{ fontSize:10, fill:"var(--text-secondary)" }}
                 axisLine={false} tickLine={false}
                 tickFormatter={v => v.toFixed(3)} />
          <YAxis type="category" dataKey="feature" width={180}
                 tick={{ fontSize:11, fill:"var(--text-secondary)" }}
                 axisLine={false} tickLine={false} />
          <Tooltip content={<ShapTooltip />} cursor={{ fill:"rgba(255,255,255,.03)" }} />
          <ReferenceLine x={0} stroke="var(--border)" />
          <Bar dataKey="shap_value" radius={[0,4,4,0]} barSize={14}>
            {data.map((d,i) => (
              <Cell key={i} fill={d.shap_value > 0 ? "var(--grade-d)" : "var(--grade-a)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function Field({ label, value, mono }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:3 }}>
      <div style={{ fontSize:11, color:"var(--text-secondary)", textTransform:"uppercase", letterSpacing:".04em" }}>{label}</div>
      <div className={mono ? "mono" : ""} style={{ fontSize:13, color:"var(--text-primary)" }}>{value || "—"}</div>
    </div>
  );
}

// ── NEW: Decision badge ────────────────────────────────────────────────────

function DecisionBadge({ decision }) {
  if (!decision) return null;

  const COLOR = {
    APPROVE: { bg: "var(--grade-a)", label: "Approve" },
    REFER:   { bg: "var(--grade-c)", label: "Refer — manual review" },
    DECLINE: { bg: "var(--grade-e)", label: "Decline" },
  };
  const c = COLOR[decision.decision] || COLOR.REFER;

  return (
    <div style={{
      background:"var(--bg-card)", border:`1px solid ${c.bg}66`,
      borderRadius:"var(--r-lg)", padding:24,
    }}>
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:14 }}>
        <span style={{
          background:c.bg+"22", color:c.bg, border:`1px solid ${c.bg}55`,
          borderRadius:6, padding:"6px 16px", fontFamily:"var(--font-mono)",
          fontWeight:600, fontSize:15,
        }}>
          {c.label}
        </span>
        <span style={{ fontSize:11, color:"var(--text-muted)" }}>
          confidence: {decision.confidence}
        </span>
      </div>

      <div style={{ fontSize:11, color:"var(--text-secondary)", textTransform:"uppercase",
                     letterSpacing:".04em", marginBottom:8 }}>
        Reasoning
      </div>
      <ul style={{ margin:0, paddingLeft:18, fontSize:13, color:"var(--text-primary)", lineHeight:1.7 }}>
        {decision.reasoning.map((r, i) => <li key={i}>{r}</li>)}
      </ul>

      {decision.policy_refs?.length > 0 && (
        <div style={{ marginTop:14, display:"flex", flexWrap:"wrap", gap:6 }}>
          {decision.policy_refs.map((p, i) => (
            <span key={i} style={{
              fontSize:11, background:"var(--bg-surface)", border:"1px solid var(--border)",
              borderRadius:4, padding:"2px 8px", color:"var(--text-secondary)",
            }}>
              {p}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── NEW: Model comparison panel ─────────────────────────────────────────────

function ModelComparison({ pred }) {
  if (!pred) return null;
  const rf = pred.pd_probability_rf ?? 0;
  const lr = pred.pd_probability_lr ?? 0;
  const diff = Math.abs(rf - lr);
  const agree = diff < 0.10; // within 10 points = agreement

  const Bar = ({ label, value, color }) => (
    <div style={{ marginBottom:12 }}>
      <div style={{ display:"flex", justifyContent:"space-between", fontSize:12, marginBottom:4 }}>
        <span style={{ color:"var(--text-secondary)" }}>{label}</span>
        <span className="mono" style={{ color, fontWeight:600 }}>{(value*100).toFixed(2)}%</span>
      </div>
      <div style={{ height:8, background:"var(--bg-hover)", borderRadius:4, overflow:"hidden" }}>
        <div style={{ width:`${Math.min(100,value*100)}%`, height:"100%", background:color, borderRadius:4 }} />
      </div>
    </div>
  );

  return (
    <div style={{
      background:"var(--bg-card)", border:"1px solid var(--border)",
      borderRadius:"var(--r-lg)", padding:24,
    }}>
      <h2 style={{ fontSize:14, fontWeight:500, marginBottom:4 }}>Model comparison</h2>
      <p style={{ fontSize:12, color:"var(--text-secondary)", marginBottom:18 }}>
        Random Forest vs Logistic Regression — same application, two models.
      </p>

      <Bar label="Random Forest"        value={rf} color="var(--teal)" />
      <Bar label="Logistic Regression"  value={lr} color="var(--grade-b)" />

      <div style={{
        marginTop:14, paddingTop:14, borderTop:"1px solid var(--border)",
        display:"flex", alignItems:"center", gap:8, fontSize:12,
      }}>
        {agree ? (
          <>
            <span style={{ color:"var(--grade-a)" }}>●</span>
            <span style={{ color:"var(--text-secondary)" }}>
              Models agree — difference of {(diff*100).toFixed(1)} points
            </span>
          </>
        ) : (
          <>
            <span style={{ color:"var(--grade-d)" }}>●</span>
            <span style={{ color:"var(--text-secondary)" }}>
              Models disagree — difference of {(diff*100).toFixed(1)} points.
              Consider manual review.
            </span>
          </>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CustomerProfile() {
  const [inputId,  setInputId]  = useState("");
  const [appId,    setAppId]    = useState(null);
  const [pred,     setPred]     = useState(null);
  const [explain,  setExplain]  = useState(null);
  const [decision, setDecision] = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);

  const handleSearch = async () => {
    const id = inputId.trim().toUpperCase();
    if (!id) return;
    setAppId(id); setLoading(true); setError(null);
    setPred(null); setExplain(null); setDecision(null);

    try {
      const [p, e, d] = await Promise.all([
        getPrediction(id),
        getExplanation(id, 12),
        getDecision(id).catch(() => null), // don't fail the whole page if decision errors
      ]);
      setPred(p);
      setExplain(e);
      setDecision(d);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const isHighRisk = pred && ["D","E"].includes(pred.risk_grade);

  return (
    <div className="fade-in">
      {/* Header */}
      <div style={{ marginBottom:28 }}>
        <h1 style={{ fontSize:20, fontWeight:600 }}>Application Lookup</h1>
        <p style={{ color:"var(--text-secondary)", fontSize:13, marginTop:4 }}>
          Enter an application ID to view PD score, SHAP risk drivers, and customer profile.
        </p>
      </div>

      {/* Search bar */}
      <div style={{ display:"flex", gap:10, marginBottom:28 }}>
        <div style={{
          flex:1, display:"flex", alignItems:"center", gap:10,
          background:"var(--bg-card)", border:"1px solid var(--border)",
          borderRadius:"var(--r-md)", padding:"0 14px",
        }}>
          <Search size={15} style={{ color:"var(--text-secondary)", flexShrink:0 }} />
          <input
            value={inputId}
            onChange={e => setInputId(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSearch()}
            placeholder="e.g. APP000042"
            style={{
              flex:1, background:"none", border:"none", outline:"none",
              color:"var(--text-primary)", fontSize:13, fontFamily:"var(--font-mono)",
              padding:"12px 0",
            }}
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={loading}
          style={{
            background:"var(--teal)", color:"#fff", border:"none",
            borderRadius:"var(--r-md)", padding:"0 20px", fontSize:13,
            fontWeight:500, cursor:loading ? "wait":"pointer",
            opacity: loading ? .7 : 1, transition:"opacity .15s",
          }}
        >
          {loading ? "Loading…" : "Look up"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background:"var(--bg-card)", border:"1px solid var(--grade-e)",
          borderRadius:"var(--r-lg)", padding:"14px 18px",
          color:"var(--grade-e)", fontSize:13, display:"flex", gap:10,
          alignItems:"center", marginBottom:20,
        }}>
          <AlertCircle size={16} />{error}
        </div>
      )}

      {/* Results */}
      {pred && (
        <div style={{ display:"grid", gridTemplateColumns:"340px 1fr", gap:20 }}>

          {/* Left — score card */}
          <div style={{ display:"flex", flexDirection:"column", gap:16 }}>

            {/* Risk badge card */}
            <div style={{
              background:"var(--bg-card)", border:`1px solid ${GRADE_COLOR[pred.risk_grade] || "var(--border)"}44`,
              borderRadius:"var(--r-lg)", padding:24,
            }}>
              <div style={{ fontSize:12, color:"var(--text-secondary)", marginBottom:8 }}>
                {pred.application_id} · {pred.model_version}
              </div>
              <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:16 }}>
                <GradeBadge grade={pred.risk_grade} />
                {isHighRisk
                  ? <span style={{ display:"flex", alignItems:"center", gap:4, fontSize:12, color:"var(--grade-d)" }}><TrendingUp size={12}/>High risk</span>
                  : <span style={{ display:"flex", alignItems:"center", gap:4, fontSize:12, color:"var(--grade-a)" }}><TrendingDown size={12}/>Low risk</span>
                }
              </div>
              <PdGauge value={pred.pd_probability_ens} />
              <div style={{
                display:"grid", gridTemplateColumns:"1fr 1fr", gap:8,
                marginTop:16, paddingTop:16, borderTop:"1px solid var(--border)",
              }}>
                <div style={{ fontSize:11, color:"var(--text-secondary)" }}>
                  RF model<br/>
                  <span className="mono" style={{ fontSize:13, color:"var(--text-primary)" }}>{fmt(pred.pd_probability_rf)}</span>
                </div>
                <div style={{ fontSize:11, color:"var(--text-secondary)" }}>
                  LR model<br/>
                  <span className="mono" style={{ fontSize:13, color:"var(--text-primary)" }}>{fmt(pred.pd_probability_lr)}</span>
                </div>
              </div>
              <div style={{ marginTop:12, fontSize:11, color:"var(--text-muted)" }}>
                Ensemble: RF 70% + LR 30%
              </div>
            </div>

            {/* Customer fields */}
            <div style={{
              background:"var(--bg-card)", border:"1px solid var(--border)",
              borderRadius:"var(--r-lg)", padding:24,
              display:"grid", gridTemplateColumns:"1fr 1fr", gap:16,
            }}>
              <Field label="Customer ID"    value={pred.customer_id} mono />
              <Field label="Loan Purpose"   value={pred.loan_purpose} />
              <Field label="Loan Amount"    value={fmtN(pred.loan_amount_inr) + " ₹"} mono />
              <Field label="Annual Income"  value={fmtN(pred.annual_income_inr) + " ₹"} mono />
              <Field label="DTI Ratio"      value={fmtF(pred.dti_ratio, 3)} mono />
              <Field label="DTI Tier"       value={pred.dti_risk_tier} />
              <Field label="Credit Score"   value={pred.credit_score} mono />
              <Field label="Employment"     value={pred.employment_type} />
              <Field label="LTI Ratio"      value={fmtF(pred.loan_to_income_ratio, 3)} mono />
              <Field label="Risk Tier"      value={pred.credit_risk_tier} />
            </div>

            {/* NEW: Decision badge */}
            <DecisionBadge decision={decision} />

            {/* NEW: Model comparison */}
            <ModelComparison pred={pred} />

            {/* Cache info */}
            <div style={{ fontSize:11, color:"var(--text-muted)", display:"flex", gap:6, alignItems:"center" }}>
              {pred.cache_hit
                ? <><CheckCircle size={11} style={{color:"var(--grade-a)"}} /> Served from Redis cache</>
                : <>Live DB query</>
              }
              <span style={{ marginLeft:"auto" }}>{pred.latency_ms}ms</span>
            </div>
          </div>

          {/* Right — SHAP chart */}
          <div style={{
            background:"var(--bg-card)", border:"1px solid var(--border)",
            borderRadius:"var(--r-lg)", padding:24,
          }}>
            <h2 style={{ fontSize:14, fontWeight:500, marginBottom:4 }}>SHAP Risk Drivers</h2>
            <p style={{ fontSize:12, color:"var(--text-secondary)", marginBottom:20 }}>
              Features that most influenced this application's PD score.
              Positive SHAP → increases default probability · Negative → reduces it.
            </p>
            <ShapChart drivers={explain?.risk_drivers} />
          </div>
        </div>
      )}

      {/* Empty state */}
      {!pred && !loading && !error && (
        <div style={{
          background:"var(--bg-card)", border:"1px solid var(--border)",
          borderRadius:"var(--r-lg)", padding:"60px 40px", textAlign:"center",
          color:"var(--text-secondary)", fontSize:13,
        }}>
          <Search size={32} style={{ marginBottom:12, opacity:.3 }} />
          <div>Enter an application ID above to view its credit risk profile.</div>
          <div style={{ marginTop:6, fontSize:12, color:"var(--text-muted)", fontFamily:"var(--font-mono)" }}>
            Try: APP000001 · APP000042 · APP000100
          </div>
        </div>
      )}
    </div>
  );
}
