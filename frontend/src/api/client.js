// src/api/client.js — complete with all endpoints including model registry
const BASE = "/api";

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

// ── Risk endpoints ─────────────────────────────────────────────────────────
export const getPortfolio     = ()               => apiFetch("/risk/portfolio");
export const getPrediction    = (appId, ver=null) => apiFetch(`/risk/predict/${appId}${ver ? `?model_version=${ver}` : ""}`);
export const getExplanation   = (appId, n=10)    => apiFetch(`/risk/explain/${appId}?top_n=${n}`);
export const getDecision      = (appId)          => apiFetch(`/risk/decide/${appId}`);
export const getCustomer      = (custId)         => apiFetch(`/risk/customer/${custId}`);
export const batchPredict     = (ids)            => apiFetch("/risk/predict/batch", {
  method: "POST", body: JSON.stringify({ application_ids: ids }),
});

// ── Model registry endpoints ───────────────────────────────────────────────
export const getModels        = ()      => apiFetch("/risk/models");
export const getModel         = (ver)   => apiFetch(`/risk/models/${ver}`);
export const promoteModel     = (ver)   => apiFetch(`/risk/models/${ver}/promote`, { method: "POST" });

// ── Monitoring endpoints ───────────────────────────────────────────────────
export const getMonitoring    = ()      => apiFetch("/risk/monitoring");
export const getMonitoringLatest = ()   => apiFetch("/risk/monitoring/latest");

// ── Analyst endpoints ──────────────────────────────────────────────────────
export const askAnalyst       = (question, application_id=null) =>
  apiFetch("/analyst/ask", { method:"POST", body: JSON.stringify({ question, application_id }) });
export const explainApplication = (appId) =>
  apiFetch(`/analyst/explain/${appId}`, { method:"POST" });
export const analystHealth    = () => apiFetch("/analyst/health");
