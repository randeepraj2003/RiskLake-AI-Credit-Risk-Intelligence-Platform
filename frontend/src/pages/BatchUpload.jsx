// src/pages/BatchUpload.jsx
// Upload a CSV of application_ids, get back a scored CSV (PD + grade + decision)
// Calls: POST /api/risk/predict/batch-csv

import { useState, useRef } from "react";
import { Upload, Download, FileText, AlertCircle, CheckCircle } from "lucide-react";

export default function BatchUpload() {
  const [file,     setFile]     = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);
  const [resultBlobUrl, setResultBlobUrl] = useState(null);
  const [rowCount, setRowCount] = useState(null);
  const fileRef = useRef(null);

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setFile(f);
    setError(null);
    setResultBlobUrl(null);
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResultBlobUrl(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/risk/predict/batch-csv", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `Upload failed (${res.status})`);
      }

      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      setResultBlobUrl(url);

      // Count rows for display
      const text = await blob.text();
      const lines = text.trim().split("\n");
      setRowCount(Math.max(0, lines.length - 1));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setFile(null);
    setResultBlobUrl(null);
    setError(null);
    setRowCount(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="fade-in">
      <div style={{ marginBottom:28 }}>
        <h1 style={{ fontSize:20, fontWeight:600 }}>Batch scoring</h1>
        <p style={{ color:"var(--text-secondary)", fontSize:13, marginTop:4 }}>
          Upload a CSV with an <code style={{fontFamily:"var(--font-mono)"}}>application_id</code> column.
          Get back PD scores, risk grades, and approve/refer/decline decisions for every row.
        </p>
      </div>

      <div style={{
        background:"var(--bg-card)", border:"1px dashed var(--border)",
        borderRadius:"var(--r-lg)", padding:40, textAlign:"center",
      }}>
        <Upload size={32} style={{ color:"var(--text-muted)", marginBottom:14 }} />

        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          onChange={handleFileChange}
          style={{ display:"none" }}
          id="csv-upload"
        />
        <label htmlFor="csv-upload" style={{
          display:"inline-block", background:"var(--bg-hover)",
          border:"1px solid var(--border)", borderRadius:"var(--r-md)",
          padding:"10px 20px", fontSize:13, cursor:"pointer", color:"var(--text-primary)",
        }}>
          Choose CSV file
        </label>

        {file && (
          <div style={{ marginTop:16, display:"flex", alignItems:"center", justifyContent:"center", gap:8 }}>
            <FileText size={14} style={{ color:"var(--teal)" }} />
            <span style={{ fontSize:13, color:"var(--text-primary)" }}>{file.name}</span>
            <span style={{ fontSize:11, color:"var(--text-muted)" }}>
              ({(file.size / 1024).toFixed(1)} KB)
            </span>
          </div>
        )}

        {file && !resultBlobUrl && (
          <button
            onClick={handleUpload}
            disabled={loading}
            style={{
              marginTop:20, background:"var(--teal)", color:"#fff", border:"none",
              borderRadius:"var(--r-md)", padding:"10px 24px", fontSize:13,
              fontWeight:500, cursor:loading ? "wait" : "pointer",
              opacity: loading ? .7 : 1,
            }}
          >
            {loading ? "Scoring applications…" : "Score applications"}
          </button>
        )}

        <div style={{ marginTop:18, fontSize:11, color:"var(--text-muted)" }}>
          Maximum 500 rows per upload · CSV must include an application_id column
        </div>
      </div>

      {error && (
        <div style={{
          marginTop:16, background:"var(--bg-card)", border:"1px solid var(--grade-e)",
          borderRadius:"var(--r-lg)", padding:"14px 18px", color:"var(--grade-e)",
          fontSize:13, display:"flex", gap:10, alignItems:"center",
        }}>
          <AlertCircle size={16} />{error}
        </div>
      )}

      {resultBlobUrl && (
        <div style={{
          marginTop:16, background:"var(--bg-card)", border:"1px solid var(--grade-a)",
          borderRadius:"var(--r-lg)", padding:24,
          display:"flex", alignItems:"center", justifyContent:"space-between",
        }}>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <CheckCircle size={18} style={{ color:"var(--grade-a)" }} />
            <div>
              <div style={{ fontSize:13, color:"var(--text-primary)" }}>
                Scored {rowCount} application{rowCount === 1 ? "" : "s"}
              </div>
              <div style={{ fontSize:11, color:"var(--text-secondary)" }}>
                Results include PD score, risk grade, and decision for each row
              </div>
            </div>
          </div>
          <div style={{ display:"flex", gap:10 }}>
            <a
              href={resultBlobUrl}
              download="risklake_batch_results.csv"
              style={{
                background:"var(--teal)", color:"#fff", borderRadius:"var(--r-md)",
                padding:"8px 16px", fontSize:13, fontWeight:500, textDecoration:"none",
                display:"flex", alignItems:"center", gap:6,
              }}
            >
              <Download size={14} /> Download results
            </a>
            <button onClick={reset} style={{
              background:"none", border:"1px solid var(--border)", borderRadius:"var(--r-md)",
              padding:"8px 16px", fontSize:13, color:"var(--text-secondary)", cursor:"pointer",
            }}>
              Upload another
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
