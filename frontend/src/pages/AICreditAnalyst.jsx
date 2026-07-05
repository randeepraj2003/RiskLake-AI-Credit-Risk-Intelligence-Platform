// src/pages/AICreditAnalyst.jsx
// AI credit analyst chat — powered by RAG (ChromaDB + Gemini).
// Optionally scoped to a specific application_id for SHAP-grounded answers.
// Calls: POST /api/analyst/ask

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, BookOpen, Loader, AlertCircle, X } from "lucide-react";
import { askAnalyst } from "../api/client.js";

// ── Suggested questions ───────────────────────────────────────────────────────

const SUGGESTIONS = [
  "What DTI ratio triggers a decline recommendation under RBI guidelines?",
  "Explain the Basel III PD risk grades A through E.",
  "What is the minimum credit score for an unsecured personal loan?",
  "What early warning indicators should I monitor for credit stress?",
  "What happens when a credit stress score reaches 3 or above?",
  "Explain the collateral coverage ratio requirement for home loans.",
];

// ── Message bubble ────────────────────────────────────────────────────────────

function Message({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div style={{
      display:"flex", gap:12, padding:"16px 0",
      borderBottom:"1px solid var(--border-light)",
      flexDirection: isUser ? "row-reverse" : "row",
    }}>
      {/* Avatar */}
      <div style={{
        width:32, height:32, borderRadius:"50%", flexShrink:0,
        background: isUser ? "var(--teal-dim)" : "var(--bg-hover)",
        display:"flex", alignItems:"center", justifyContent:"center",
        border: isUser ? "1px solid var(--teal)" : "1px solid var(--border)",
      }}>
        {isUser ? <User size={14} style={{ color:"var(--teal)" }} />
                : <Bot  size={14} style={{ color:"var(--text-secondary)" }} />}
      </div>

      <div style={{ flex:1, maxWidth:"85%" }}>
        {/* Answer text */}
        <div style={{
          background: isUser ? "var(--teal-glow)" : "var(--bg-card)",
          border: `1px solid ${isUser ? "var(--teal-dim)" : "var(--border)"}`,
          borderRadius:"var(--r-lg)", padding:"12px 16px",
          fontSize:13, lineHeight:1.7, color:"var(--text-primary)",
          whiteSpace:"pre-wrap",
        }}>
          {msg.content}
        </div>

        {/* Sources */}
        {msg.sources?.length > 0 && (
          <div style={{ marginTop:8, display:"flex", flexWrap:"wrap", gap:6 }}>
            {msg.sources.map((s, i) => (
              <span key={i} style={{
                display:"flex", alignItems:"center", gap:4, fontSize:11,
                background:"var(--bg-surface)", border:"1px solid var(--border)",
                borderRadius:4, padding:"2px 8px", color:"var(--text-secondary)",
              }}>
                <BookOpen size={10} />
                {s.source.replace(/_/g," ")} · {s.section}
              </span>
            ))}
          </div>
        )}

        {/* Timing */}
        {msg.meta && (
          <div style={{ fontSize:10, color:"var(--text-muted)", marginTop:6, fontFamily:"var(--font-mono)" }}>
            retrieval {msg.meta.retrieval_ms}ms · generation {msg.meta.generation_ms}ms · {msg.meta.tokens_used} tokens
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AICreditAnalyst() {
  const [messages,   setMessages]   = useState([]);
  const [input,      setInput]      = useState("");
  const [appId,      setAppId]      = useState("");
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior:"smooth" });
  }, [messages, loading]);

  const send = async (question) => {
    const q = (question || input).trim();
    if (!q || loading) return;

    setInput("");
    setError(null);
    setMessages(prev => [...prev, { role:"user", content:q }]);
    setLoading(true);

    try {
      const res = await askAnalyst(q, appId.trim().toUpperCase() || null);
      setMessages(prev => [...prev, {
        role:    "assistant",
        content: res.answer,
        sources: res.sources,
        meta:    {
          retrieval_ms:  res.retrieval_ms,
          generation_ms: res.generation_ms,
          tokens_used:   res.tokens_used,
        },
      }]);
    } catch (err) {
      setError(err.message);
      setMessages(prev => [...prev, {
        role:    "assistant",
        content: `Error: ${err.message}`,
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const clearChat = () => {
    setMessages([]);
    setError(null);
    setInput("");
  };

  return (
    <div className="fade-in" style={{ display:"flex", flexDirection:"column", height:"calc(100vh - 56px)" }}>

      {/* Header */}
      <div style={{ marginBottom:20 }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between" }}>
          <div>
            <h1 style={{ fontSize:20, fontWeight:600 }}>AI Credit Analyst</h1>
            <p style={{ color:"var(--text-secondary)", fontSize:13, marginTop:4 }}>
              RAG pipeline · ChromaDB + Gemini 1.5 Flash · Grounded in RBI, Basel III, and product guidelines
            </p>
          </div>
          {messages.length > 0 && (
            <button onClick={clearChat} style={{
              background:"none", border:"1px solid var(--border)",
              borderRadius:"var(--r-md)", padding:"6px 12px",
              color:"var(--text-secondary)", fontSize:12, cursor:"pointer",
              display:"flex", alignItems:"center", gap:6,
            }}>
              <X size={12}/> Clear chat
            </button>
          )}
        </div>

        {/* Application scope bar */}
        <div style={{
          marginTop:16, background:"var(--bg-card)", border:"1px solid var(--border)",
          borderRadius:"var(--r-md)", padding:"10px 16px",
          display:"flex", alignItems:"center", gap:12,
        }}>
          <span style={{ fontSize:12, color:"var(--text-secondary)", whiteSpace:"nowrap" }}>
            Scope to application (optional):
          </span>
          <input
            value={appId}
            onChange={e => setAppId(e.target.value)}
            placeholder="e.g. APP000042 — injects PD score + SHAP context"
            style={{
              flex:1, background:"none", border:"none", outline:"none",
              color:"var(--text-primary)", fontSize:12, fontFamily:"var(--font-mono)",
            }}
          />
          {appId && (
            <span style={{
              fontSize:11, background:"var(--teal-glow)", color:"var(--teal)",
              border:"1px solid var(--teal-dim)", borderRadius:4, padding:"2px 8px",
            }}>
              SHAP context ON
            </span>
          )}
        </div>
      </div>

      {/* Messages area */}
      <div style={{
        flex:1, overflow:"auto", background:"var(--bg-surface)",
        border:"1px solid var(--border)", borderRadius:"var(--r-lg)",
        padding:"0 20px", marginBottom:16,
      }}>
        {/* Empty state / suggestions */}
        {messages.length === 0 && (
          <div style={{ padding:"32px 0" }}>
            <div style={{ textAlign:"center", marginBottom:28 }}>
              <Bot size={36} style={{ color:"var(--text-muted)", marginBottom:10 }} />
              <div style={{ fontSize:14, fontWeight:500, color:"var(--text-secondary)" }}>
                Ask anything about credit risk, policy thresholds, or a specific application.
              </div>
              <div style={{ fontSize:12, color:"var(--text-muted)", marginTop:6 }}>
                Answers are grounded in RBI guidelines, Basel III, AML typologies, and internal product rules.
              </div>
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10 }}>
              {SUGGESTIONS.map((s, i) => (
                <button key={i} onClick={() => send(s)} style={{
                  background:"var(--bg-card)", border:"1px solid var(--border)",
                  borderRadius:"var(--r-md)", padding:"12px 14px", textAlign:"left",
                  color:"var(--text-secondary)", fontSize:12, cursor:"pointer",
                  lineHeight:1.5, transition:"border-color .15s",
                }}
                  onMouseEnter={e => e.currentTarget.style.borderColor="var(--teal)"}
                  onMouseLeave={e => e.currentTarget.style.borderColor="var(--border)"}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message list */}
        {messages.map((msg, i) => <Message key={i} msg={msg} />)}

        {/* Loading indicator */}
        {loading && (
          <div style={{ display:"flex", gap:12, padding:"16px 0", alignItems:"center" }}>
            <div style={{
              width:32, height:32, borderRadius:"50%",
              background:"var(--bg-hover)", border:"1px solid var(--border)",
              display:"flex", alignItems:"center", justifyContent:"center",
            }}>
              <Bot size={14} style={{ color:"var(--text-secondary)" }} />
            </div>
            <div style={{ display:"flex", gap:5, alignItems:"center" }}>
              {[0,1,2].map(i => (
                <div key={i} style={{
                  width:7, height:7, borderRadius:"50%",
                  background:"var(--teal)", opacity:.5,
                  animation:`pulse 1.2s ease-in-out ${i*0.2}s infinite`,
                }} />
              ))}
              <span style={{ fontSize:12, color:"var(--text-secondary)", marginLeft:6 }}>
                Retrieving policy context…
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Error */}
      {error && (
        <div style={{
          marginBottom:12, padding:"10px 14px", borderRadius:"var(--r-md)",
          background:"var(--bg-card)", border:"1px solid var(--grade-e)",
          color:"var(--grade-e)", fontSize:12, display:"flex", gap:8, alignItems:"center",
        }}>
          <AlertCircle size={14}/>{error}
        </div>
      )}

      {/* Input bar */}
      <div style={{
        display:"flex", gap:10, background:"var(--bg-card)",
        border:"1px solid var(--border)", borderRadius:"var(--r-lg)",
        padding:"10px 14px", alignItems:"flex-end",
      }}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          placeholder="Ask about credit policy, risk thresholds, or a specific application… (Enter to send)"
          rows={1}
          style={{
            flex:1, background:"none", border:"none", outline:"none", resize:"none",
            color:"var(--text-primary)", fontSize:13, lineHeight:1.6,
            fontFamily:"var(--font-ui)", maxHeight:120, overflow:"auto",
          }}
          onInput={e => {
            e.target.style.height = "auto";
            e.target.style.height = e.target.scrollHeight + "px";
          }}
        />
        <button
          onClick={() => send()}
          disabled={loading || !input.trim()}
          style={{
            background:"var(--teal)", color:"#fff", border:"none",
            borderRadius:"var(--r-md)", width:36, height:36, display:"flex",
            alignItems:"center", justifyContent:"center", cursor:"pointer",
            flexShrink:0, opacity: (loading || !input.trim()) ? .4 : 1,
            transition:"opacity .15s",
          }}
        >
          {loading ? <Loader size={15} style={{ animation:"spin 1s linear infinite" }} />
                   : <Send size={15} />}
        </button>
      </div>

      <div style={{ fontSize:11, color:"var(--text-muted)", marginTop:8, textAlign:"center" }}>
        Answers grounded in ChromaDB policy retrieval · Powered by Gemini 1.5 Flash · Not financial advice
      </div>
    </div>
  );
}
