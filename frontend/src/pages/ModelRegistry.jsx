// src/pages/ModelRegistry.jsx
// Shows all model versions in gold.model_registry with metrics comparison.
// Also shows drift detection history from gold.model_monitoring.
// Calls: GET /api/risk/models
//        GET /api/risk/monitoring/latest
//        POST /api/risk/models/{version}/promote

import { useState, useEffect } from "react";
import { AlertTriangle, CheckCircle, Clock, TrendingUp, RefreshCw } from "lucide-react";

const BASE = "/api";
const apiFetch = (path, opts={}) => fetch(`${BASE}${path}`, {
  headers:{"Content-Type":"application/json"}, ...opts
}).then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail || r.statusText) }));

const getModels  = ()      => apiFetch("/risk/models");
const getLatest  = ()      => apiFetch("/risk/monitoring/latest");
const promote    = (ver)   => apiFetch(`/risk/models/${ver}/promote`, { method:"POST" });

const fmt4 = n => n == null ? "—" : Number(n).toFixed(4);
const fmtPct = n => n == null ? "—" : Number(n).toFixed(2) + "%";

const STATUS_COLOR = {
  active:    "#3fb950",
  candidate: "#58a6ff",
  retired:   "#484f58",
};

const DRIFT_COLOR = {
  none:     "#3fb950",
  minor:    "#e3b341",
  moderate: "#f78166",
  severe:   "#ff7b72",
};

function StatusBadge({ status }) {
  const color = STATUS_COLOR[status] || "#888";
  return (
    <span style={{
      background: color + "22", color, border: `1px solid ${color}55`,
      borderRadius: 4, padding: "2px 10px", fontSize: 11,
      fontFamily: "var(--font-mono)", fontWeight: 600,
    }}>
      {status}
    </span>
  );
}

function DriftBadge({ severity, detected }) {
  if (!detected) return (
    <span style={{ display:"flex", alignItems:"center", gap:4, fontSize:12, color:"#3fb950" }}>
      <CheckCircle size={12} /> No drift
    </span>
  );
  const color = DRIFT_COLOR[severity] || "#888";
  return (
    <span style={{
      display:"flex", alignItems:"center", gap:4, fontSize:12, color,
    }}>
      <AlertTriangle size={12} /> {severity} drift
    </span>
  );
}

export default function ModelRegistry() {
  const [models,   setModels]   = useState([]);
  const [latest,   setLatest]   = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [promoting, setPromoting] = useState(null);
  const [promoteMsg, setPromoteMsg] = useState(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const [m, l] = await Promise.all([getModels(), getLatest().catch(() => null)]);
      setModels(m.models || []);
      setLatest(l);
    } catch(e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handlePromote = async (version) => {
    setPromoting(version); setPromoteMsg(null);
    try {
      const res = await promote(version);
      setPromoteMsg({ type:"success", text: res.message });
      await load();
    } catch(e) {
      setPromoteMsg({ type:"error", text: e.message });
    } finally {
      setPromoting(null);
    }
  };

  const activeModel = models.find(m => m.status === "active");

  return (
    <div className="fade-in">
      {/* Header */}
      <div style={{ marginBottom:28, display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
        <div>
          <h1 style={{ fontSize:20, fontWeight:600 }}>Model Registry</h1>
          <p style={{ color:"var(--text-secondary)", fontSize:13, marginTop:4 }}>
            A/B model versioning · drift detection · promote candidate to active
          </p>
        </div>
        <button onClick={load} style={{
          background:"none", border:"1px solid var(--border)", borderRadius:"var(--r-md)",
          padding:"8px 14px", fontSize:12, color:"var(--text-secondary)", cursor:"pointer",
          display:"flex", alignItems:"center", gap:6,
        }}>
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {error && (
        <div style={{
          background:"var(--bg-card)", border:"1px solid var(--grade-e)",
          borderRadius:"var(--r-lg)", padding:"14px 18px", color:"var(--grade-e)",
          fontSize:13, marginBottom:20,
        }}>
          {error}
        </div>
      )}

      {promoteMsg && (
        <div style={{
          background:"var(--bg-card)",
          border:`1px solid ${promoteMsg.type === "success" ? "var(--grade-a)" : "var(--grade-e)"}`,
          borderRadius:"var(--r-lg)", padding:"12px 18px",
          color: promoteMsg.type === "success" ? "var(--grade-a)" : "var(--grade-e)",
          fontSize:13, marginBottom:20,
        }}>
          {promoteMsg.text}
        </div>
      )}

      {/* Drift alert banner */}
      {latest?.drift_detected && (
        <div style={{
          background: DRIFT_COLOR[latest.drift_severity] + "15",
          border:`1px solid ${DRIFT_COLOR[latest.drift_severity]}55`,
          borderRadius:"var(--r-lg)", padding:"14px 20px", marginBottom:20,
          display:"flex", alignItems:"center", gap:12,
        }}>
          <AlertTriangle size={18} style={{ color: DRIFT_COLOR[latest.drift_severity], flexShrink:0 }} />
          <div>
            <div style={{ fontWeight:500, fontSize:13, color:"var(--text-primary)" }}>
              {latest.drift_severity.charAt(0).toUpperCase() + latest.drift_severity.slice(1)} drift detected
            </div>
            <div style={{ fontSize:12, color:"var(--text-secondary)", marginTop:2 }}>
              KS statistic {latest.ks_statistic?.toFixed(4)} (p={latest.ks_pvalue?.toFixed(4)})
              on {latest.snapshot_date} · {latest.total_scored} applications scored
            </div>
          </div>
        </div>
      )}

      {/* Active model summary */}
      {activeModel && (
        <div style={{
          background:"var(--bg-card)", border:"1px solid var(--teal)44",
          borderRadius:"var(--r-lg)", padding:24, marginBottom:20,
          display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:20,
        }}>
          <div>
            <div style={{ fontSize:11, color:"var(--text-secondary)", textTransform:"uppercase", letterSpacing:".04em", marginBottom:4 }}>Active model</div>
            <div style={{ fontSize:18, fontWeight:600, fontFamily:"var(--font-mono)", color:"var(--teal)" }}>{activeModel.model_version}</div>
          </div>
          <div>
            <div style={{ fontSize:11, color:"var(--text-secondary)", textTransform:"uppercase", letterSpacing:".04em", marginBottom:4 }}>Ensemble AUC</div>
            <div style={{ fontSize:18, fontWeight:600, fontFamily:"var(--font-mono)" }}>{fmt4(activeModel.ensemble_auc)}</div>
          </div>
          <div>
            <div style={{ fontSize:11, color:"var(--text-secondary)", textTransform:"uppercase", letterSpacing:".04em", marginBottom:4 }}>Drift status</div>
            <div style={{ fontSize:15, fontWeight:500 }}>
              {latest ? <DriftBadge severity={latest.drift_severity} detected={latest.drift_detected} /> : "—"}
            </div>
          </div>
          <div>
            <div style={{ fontSize:11, color:"var(--text-secondary)", textTransform:"uppercase", letterSpacing:".04em", marginBottom:4 }}>Trained</div>
            <div style={{ fontSize:13, color:"var(--text-secondary)" }}>
              {activeModel.trained_at ? activeModel.trained_at.slice(0,10) : "—"}
            </div>
          </div>
        </div>
      )}

      {/* Model versions table */}
      <div style={{
        background:"var(--bg-card)", border:"1px solid var(--border)",
        borderRadius:"var(--r-lg)", overflow:"hidden", marginBottom:20,
      }}>
        <div style={{ padding:"16px 24px", borderBottom:"1px solid var(--border)" }}>
          <h2 style={{ fontSize:14, fontWeight:500 }}>All model versions ({models.length})</h2>
        </div>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
          <thead>
            <tr style={{ background:"var(--bg-surface)" }}>
              {["Version","Status","Ensemble AUC","RF AUC","LR AUC","Avg Precision","Features","Trained","Action"].map(h => (
                <th key={h} style={{ padding:"10px 16px", textAlign:"left", color:"var(--text-secondary)",
                                     fontWeight:500, borderBottom:"1px solid var(--border)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} style={{ padding:24, textAlign:"center", color:"var(--text-secondary)" }}>
                Loading…
              </td></tr>
            ) : models.length === 0 ? (
              <tr><td colSpan={9} style={{ padding:24, textAlign:"center", color:"var(--text-secondary)" }}>
                No models registered yet. Run train_versioned.py to create one.
              </td></tr>
            ) : (
              models.map(m => (
                <tr key={m.model_version} style={{ borderBottom:"1px solid var(--border-light)" }}>
                  <td style={{ padding:"12px 16px", fontFamily:"var(--font-mono)", color:"var(--text-primary)" }}>
                    {m.model_version}
                  </td>
                  <td style={{ padding:"12px 16px" }}><StatusBadge status={m.status} /></td>
                  <td style={{ padding:"12px 16px", fontFamily:"var(--font-mono)",
                               color: m.status === "active" ? "var(--teal)" : "var(--text-primary)" }}>
                    {fmt4(m.ensemble_auc)}
                  </td>
                  <td style={{ padding:"12px 16px", fontFamily:"var(--font-mono)", color:"var(--text-secondary)" }}>
                    {fmt4(m.rf_auc)}
                  </td>
                  <td style={{ padding:"12px 16px", fontFamily:"var(--font-mono)", color:"var(--text-secondary)" }}>
                    {fmt4(m.lr_auc)}
                  </td>
                  <td style={{ padding:"12px 16px", fontFamily:"var(--font-mono)", color:"var(--text-secondary)" }}>
                    {fmt4(m.avg_precision)}
                  </td>
                  <td style={{ padding:"12px 16px", color:"var(--text-secondary)" }}>{m.feature_count}</td>
                  <td style={{ padding:"12px 16px", color:"var(--text-secondary)" }}>
                    {m.trained_at ? m.trained_at.slice(0,10) : "—"}
                  </td>
                  <td style={{ padding:"12px 16px" }}>
                    {m.status === "candidate" ? (
                      <button
                        onClick={() => handlePromote(m.model_version)}
                        disabled={promoting === m.model_version}
                        style={{
                          background:"var(--teal)", color:"#fff", border:"none",
                          borderRadius:"var(--r-md)", padding:"4px 12px", fontSize:11,
                          cursor: promoting ? "wait" : "pointer",
                          opacity: promoting ? .6 : 1,
                        }}
                      >
                        {promoting === m.model_version ? "Promoting…" : "Promote"}
                      </button>
                    ) : (
                      <span style={{ fontSize:11, color:"var(--text-muted)" }}>
                        {m.status === "active" ? "Active ✓" : "Retired"}
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Drift monitoring card */}
      {latest && !latest.message && (
        <div style={{
          background:"var(--bg-card)", border:"1px solid var(--border)",
          borderRadius:"var(--r-lg)", padding:24,
        }}>
          <h2 style={{ fontSize:14, fontWeight:500, marginBottom:16 }}>Latest drift snapshot — {latest.snapshot_date}</h2>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:12, marginBottom:20 }}>
            {["A","B","C","D","E"].map(g => (
              <div key={g} style={{
                background:"var(--bg-surface)", borderRadius:"var(--r-md)", padding:"12px 16px",
              }}>
                <div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>Grade {g}</div>
                <div style={{ fontSize:18, fontWeight:600, fontFamily:"var(--font-mono)",
                             color: STATUS_COLOR[g === "A" || g === "B" ? "active" : g === "C" ? "candidate" : "retired"] }}>
                  {fmtPct(latest.grade_distribution?.[g])}
                </div>
              </div>
            ))}
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:12 }}>
            <div style={{ background:"var(--bg-surface)", borderRadius:"var(--r-md)", padding:"12px 16px" }}>
              <div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>Avg PD</div>
              <div className="mono" style={{ fontSize:16, fontWeight:600 }}>{fmtPct(latest.avg_pd * 100)}</div>
            </div>
            <div style={{ background:"var(--bg-surface)", borderRadius:"var(--r-md)", padding:"12px 16px" }}>
              <div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>KS Statistic</div>
              <div className="mono" style={{ fontSize:16, fontWeight:600 }}>{latest.ks_statistic?.toFixed(4)}</div>
            </div>
            <div style={{ background:"var(--bg-surface)", borderRadius:"var(--r-md)", padding:"12px 16px" }}>
              <div style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:4 }}>Drift Severity</div>
              <div style={{ fontSize:15, fontWeight:600, color: DRIFT_COLOR[latest.drift_severity] || "#888" }}>
                {latest.drift_severity || "none"}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* How to train a new version */}
      <div style={{
        marginTop:20, background:"var(--bg-surface)", border:"1px solid var(--border)",
        borderRadius:"var(--r-lg)", padding:20,
      }}>
        <div style={{ fontSize:12, fontWeight:500, color:"var(--text-secondary)", marginBottom:10 }}>
          How to train a new model version
        </div>
        <div style={{ fontFamily:"var(--font-mono)", fontSize:12, color:"var(--text-primary)",
                       background:"var(--bg-card)", borderRadius:"var(--r-md)", padding:"10px 14px",
                       lineHeight:1.8 }}>
          <div style={{ color:"var(--text-muted)" }}># Train new version (candidate)</div>
          <div>python app/services/train_versioned.py</div>
          <div style={{ color:"var(--text-muted)", marginTop:8 }}># Train and auto-promote if AUC improves</div>
          <div>python app/services/train_versioned.py --promote</div>
          <div style={{ color:"var(--text-muted)", marginTop:8 }}># Run drift detection</div>
          <div>python app/services/drift_detection.py</div>
        </div>
      </div>
    </div>
  );
}
