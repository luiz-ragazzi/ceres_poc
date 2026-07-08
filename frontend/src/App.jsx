import { useState, useEffect, useCallback, useRef } from "react";

const API = "http://localhost:8000";

// ─── Utility ─────────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Unknown error");
  }
  return res.json();
}

function uploadWithProgress(file, docType, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API}/upload`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        let detail = xhr.statusText;
        try { detail = JSON.parse(xhr.responseText).detail || detail; } catch { /* ignore */ }
        reject(new Error(detail));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload."));
    const form = new FormData();
    form.append("file", file);
    form.append("doc_type", docType);
    xhr.send(form);
  });
}

function formatSize(bytes) {
  if (bytes == null) return "";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}
function extIcon(name) {
  return (name.split(".").pop() || "").toUpperCase().slice(0, 3);
}

// ─── Icons ───────────────────────────────────────────────────────────────────

const IconPlus = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 5v14M5 12h14"/>
  </svg>
);
const IconUploadCloud = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3v12"/><path d="M7 8l5-5 5 5"/><path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/>
  </svg>
);
const IconTrash = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 6h18"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
  </svg>
);
const IconSend = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>
  </svg>
);
const IconCopy = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 01-1-1V4a1 1 0 011-1h10a1 1 0 011 1v1"/>
  </svg>
);

const Logo = ({ small }) => (
  <svg viewBox="0 0 680 220" height={small ? 22 : 34} role="img" aria-label="Methodos">
    <path d="M 150 60 L 128 60 L 128 160 L 150 160" fill="none" stroke="#D85A30" strokeWidth="9" strokeLinecap="square"/>
    <text x="175" y="130" fontFamily="IBM Plex Sans, Arial, sans-serif" fontSize="60" fontWeight="700" fill="#14171A">Methodos</text>
    <path d="M 545 60 L 567 60 L 567 160 L 545 160" fill="none" stroke="#D85A30" strokeWidth="9" strokeLinecap="square"/>
  </svg>
);

// ─── Shared chrome: header / doc-strip / footer ─────────────────────────────

function Header({ view, onSwitch }) {
  return (
    <header className="site">
      <div className="nav-row">
        <div className="logo-mark">
          <Logo />
          <div className="divider" />
          <div className="app-name">Query Console</div>
        </div>
        <nav className="tabs">
          <button className={`tab ${view === "query" ? "active" : ""}`} onClick={() => onSwitch("query")}>Query console</button>
          <button className={`tab ${view === "config" ? "active" : ""}`} onClick={() => onSwitch("config")}>Configuration</button>
        </nav>
        <div className="status-pill"><span className="dot" /> on-premises session</div>
      </div>
    </header>
  );
}

function DocStrip({ docCount }) {
  return (
    <div className="doc-strip">
      <div className="wrap">
        <span>ENV: <b>Proof of Concept</b></span>
        <span>STORE: <b>ChromaDB (local)</b></span>
        <span>DOCS INDEXED: <b>{docCount}</b></span>
      </div>
    </div>
  );
}

function Footer() {
  return (
    <footer>
      <div className="footer-row">
        <Logo small />
        <div className="footer-meta">Document Intelligence System · Proof of Concept · fully on-premises</div>
      </div>
    </footer>
  );
}

// ─── Configuration view ──────────────────────────────────────────────────────

function ConfigView({ docCount, setDocCount }) {
  const [docTypes, setDocTypes] = useState([]);
  const [docType, setDocType] = useState("");
  const [docs, setDocs] = useState([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [pending, setPending] = useState([]); // { id, file, pct, stage, error }
  const [saving, setSaving] = useState(false);
  const fileInputRef = useRef();

  const loadDocs = useCallback(async () => {
    try {
      const d = await apiFetch("/documents");
      setDocs(d);
      setDocCount(d.length);
    } catch { /* backend not reachable yet */ }
  }, [setDocCount]);

  useEffect(() => {
    apiFetch("/doc-types").then((types) => { setDocTypes(types); setDocType(types[0]); }).catch(() => {});
    loadDocs();
  }, [loadDocs]);

  const addFiles = (files) => {
    const items = files
      .filter((f) => f.name.toLowerCase().endsWith(".pdf"))
      .map((file) => ({ id: "p" + Math.random().toString(36).slice(2, 9), file, pct: 0, stage: "Queued", error: null }));
    setPending((prev) => [...prev, ...items]);
  };

  const removePending = (id) => setPending((prev) => prev.filter((p) => p.id !== id));

  const closePanel = () => { setPanelOpen(false); setPending([]); };

  const saveAll = async () => {
    setSaving(true);
    await Promise.all(pending.map(async (item) => {
      setPending((prev) => prev.map((p) => p.id === item.id ? { ...p, stage: "Uploading" } : p));
      try {
        const result = await uploadWithProgress(item.file, docType, (pct) => {
          setPending((prev) => prev.map((p) => p.id === item.id
            ? { ...p, pct, stage: pct >= 100 ? "Processing (Docling · chunking · embedding)…" : "Uploading" }
            : p));
        });
        setPending((prev) => prev.map((p) => p.id === item.id ? { ...p, pct: 100, stage: `Indexed — ${result.chunk_count} chunks, ${result.page_count} pages` } : p));
      } catch (e) {
        setPending((prev) => prev.map((p) => p.id === item.id ? { ...p, error: e.message, stage: "Failed" } : p));
      }
    }));
    await loadDocs();
    setSaving(false);
    setTimeout(closePanel, 700);
  };

  const handleDelete = async (docId) => {
    try {
      await apiFetch(`/documents/${docId}`, { method: "DELETE" });
      const next = docs.filter((d) => d.doc_id !== docId);
      setDocs(next);
      setDocCount(next.length);
    } catch (e) {
      alert(e.message);
    }
  };

  return (
    <div className="page">
      <div className="eyebrow">Configuration</div>
      <h1>Document index</h1>
      <p className="lede">Upload the source documents that power the query console. Each PDF is converted to Markdown via Docling, chunked along its heading tree, embedded, and written into ChromaDB — while the original PDF and converted Markdown stay on disk as the audit system of record.</p>

      <div className="toolbar">
        <div className="collection-select-wrap">
          <label htmlFor="docTypeSelect">Document type</label>
          <select id="docTypeSelect" value={docType} onChange={(e) => setDocType(e.target.value)}>
            {docTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <button className="btn btn-primary" type="button" onClick={() => setPanelOpen((o) => !o)}>
          <IconPlus /> Add document
        </button>
      </div>

      <div className={`add-panel ${panelOpen ? "open" : ""}`}>
        <div className="add-panel__inner">
          <div
            className={`dropzone ${dragOver ? "drag-over" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); addFiles(Array.from(e.dataTransfer.files)); }}
          >
            <IconUploadCloud />
            <div className="dz-title">Drop files here, or click to browse</div>
            <div className="dz-sub">PDF only — indexed as "{docType}"</div>
          </div>
          <input ref={fileInputRef} type="file" multiple accept=".pdf" style={{ display: "none" }}
            onChange={(e) => { addFiles(Array.from(e.target.files)); e.target.value = ""; }} />

          <div className="pending-list">
            {pending.map((item) => (
              <div key={item.id} className={`pending-item ${item.pct >= 100 && !item.error ? "done" : ""}`}>
                <div className="pending-item__row">
                  <div className="pending-item__icon">{extIcon(item.file.name)}</div>
                  <div className="pending-item__meta">
                    <div className="pending-item__name">{item.file.name}</div>
                    <div className="pending-item__status">{formatSize(item.file.size)} · {item.error || item.stage}</div>
                  </div>
                  {!saving && (
                    <button className="pending-item__remove" type="button" onClick={() => removePending(item.id)}>✕</button>
                  )}
                </div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: item.pct + "%", background: item.error ? "var(--red)" : undefined }} />
                </div>
              </div>
            ))}
          </div>

          <div className="panel-actions">
            <button className="btn btn-ghost" type="button" onClick={closePanel} disabled={saving}>Cancel</button>
            <button className="btn btn-primary" type="button" onClick={saveAll} disabled={saving || pending.length === 0}>
              {saving ? "Indexing…" : "Save to index"}
            </button>
          </div>
        </div>
      </div>

      <div className="table-card">
        <table className="doc-table">
          <thead>
            <tr><th>Document</th><th>Type</th><th>Pages</th><th>Chunks</th><th>Added</th><th></th></tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.doc_id}>
                <td>
                  <div className="doc-name">
                    <div className="file-ico">{extIcon(d.filename)}</div>
                    <div><span className="name-text">{d.filename}</span></div>
                  </div>
                </td>
                <td><span className="tag">{d.doc_type}</span></td>
                <td>{d.page_count ?? "—"}</td>
                <td>{d.chunk_count}</td>
                <td><span className="tag">{d.uploaded_at.slice(0, 10)}</span></td>
                <td>
                  <button className="row-action" type="button" aria-label="Remove document" onClick={() => handleDelete(d.doc_id)}>
                    <IconTrash />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {docCount === 0 && <div className="empty-table">No documents indexed yet. Click "Add document" to get started.</div>}
      </div>
    </div>
  );
}

// ─── Query console view ──────────────────────────────────────────────────────

const SUGGESTIONS = [
  { label: "SOP · Deviation handling", q: "What does our SOP say about handling manufacturing deviations?" },
  { label: "CTD · Specifications", q: "What are the release specifications described in the CTD?" },
  { label: "CAPA · Root cause", q: "What root cause analysis method do our CAPA records reference?" },
  { label: "Audit · Findings", q: "Summarize the most recent audit findings and their status." },
];

function AssistantAnswer({ result }) {
  const uniqueDocs = new Set(result.sources.map((s) => s.source)).size;
  return (
    <div className="assistant-content">
      <div className="status-line">
        <span className="dot" /> answered in {result.elapsed}s · {result.sources.length} excerpt{result.sources.length !== 1 ? "s" : ""} across {uniqueDocs} document{uniqueDocs !== 1 ? "s" : ""}
      </div>
      <div className="answer-text">{result.answer}</div>
      <div className="citation-row">
        {result.sources.map((s, i) => (
          <span className="citation-chip" key={i} title={s.chunk}>
            [{i + 1}] {s.source}{s.section_path ? ` · ${s.section_path}` : ""}{s.pages ? ` · p.${s.pages}` : ""}{s.doc_type ? ` · ${s.doc_type}` : ""}
          </span>
        ))}
      </div>
      <div className="assistant-actions">
        <button className="icon-btn" type="button" aria-label="Copy answer"
          onClick={() => navigator.clipboard?.writeText(result.answer)}>
          <IconCopy />
        </button>
      </div>
    </div>
  );
}

function QueryView() {
  const [messages, setMessages] = useState([]); // { role: 'user'|'assistant', text?, result?, error? , thinking? }
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef();
  const textareaRef = useRef();

  const scrollToBottom = () => requestAnimationFrame(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  });

  const autosize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setInput("");
    setBusy(true);
    setTimeout(autosize, 0);
    setMessages((prev) => [...prev, { role: "assistant", thinking: true }]);
    scrollToBottom();

    const start = performance.now();
    try {
      const data = await apiFetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, top_k: 5 }),
      });
      const elapsed = ((performance.now() - start) / 1000).toFixed(1);
      setMessages((prev) => {
        const next = prev.slice(0, -1);
        next.push({ role: "assistant", result: { ...data, elapsed } });
        return next;
      });
    } catch (e) {
      setMessages((prev) => {
        const next = prev.slice(0, -1);
        next.push({ role: "assistant", error: e.message });
        return next;
      });
    } finally {
      setBusy(false);
      scrollToBottom();
    }
  };

  return (
    <div className="chat-shell">
      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="mark">[ ]</div>
            <h1>Ask your documents a question</h1>
            <p>Query the indexed SOPs, CTDs, CAPA records, and audit reports directly. Every answer is generated locally and cites the section it came from.</p>
            <div className="suggestion-grid">
              {SUGGESTIONS.map((s) => (
                <button className="suggestion" key={s.q} onClick={() => send(s.q)}>
                  <span className="q-label">{s.label}</span>
                  {s.q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div className={`msg ${m.role}`} key={i}>
            {m.role === "assistant" && <div className="avatar">[ ]</div>}
            {m.role === "user" && <div className="bubble-user">{m.text}</div>}
            {m.role === "assistant" && m.thinking && (
              <div className="assistant-content">
                <div className="status-line thinking"><span className="dot" /> Searching indexed documents & generating an answer</div>
              </div>
            )}
            {m.role === "assistant" && m.result && <AssistantAnswer result={m.result} />}
            {m.role === "assistant" && m.error && (
              <div className="assistant-content"><div className="answer-text">{m.error}</div></div>
            )}
          </div>
        ))}
      </div>

      <div className="composer-wrap">
        <div className="composer">
          <textarea
            ref={textareaRef}
            rows={1}
            placeholder="Ask a question about your indexed documents…"
            value={input}
            onChange={(e) => { setInput(e.target.value); autosize(); }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          />
          <button className={`composer-btn send-btn ${input.trim() ? "active" : ""}`} type="button"
            disabled={!input.trim() || busy} onClick={() => send()} aria-label="Send question">
            <IconSend />
          </button>
        </div>
        <div className="composer-hint">Answers are generated locally from indexed documents only. Always verify citations before external use.</div>
      </div>
    </div>
  );
}

// ─── Global styles (Methodos design system) ──────────────────────────────────

const GLOBAL_STYLE = `
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Serif:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root{
  --ink:#14171A; --ink-soft:#4A5251; --paper:#EEF0EA; --paper-raised:#F7F8F4;
  --line:#D6D9CF; --coral:#D85A30; --coral-dark:#B8471F; --navy:#182528;
  --highlight-soft:#FAEBC2; --highlight:#F3D27A; --green:#3E8E5A; --amber:#C08A2E; --red:#B8472F;
  --serif:'IBM Plex Serif', Georgia, serif;
  --sans:'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --mono:'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace;
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--paper); color:var(--ink); font-family:var(--sans); line-height:1.5;
  -webkit-font-smoothing:antialiased; min-height:100vh;
  background-image:linear-gradient(var(--line) 1px, transparent 1px), linear-gradient(90deg, var(--line) 1px, transparent 1px);
  background-size:64px 64px; background-position:-1px -1px;
}
button{font:inherit;}
*:focus-visible{outline:2px solid var(--coral); outline-offset:2px;}

header.site{position:sticky; top:0; z-index:50; background:rgba(238,240,234,.92); backdrop-filter:blur(8px); border-bottom:1px solid var(--line);}
.nav-row{display:flex; align-items:center; justify-content:space-between; padding:14px 28px; max-width:1180px; margin:0 auto;}
.logo-mark{display:flex; align-items:center; gap:14px;}
.logo-mark .divider{width:1px; height:22px; background:var(--line);}
.logo-mark .app-name{font-family:var(--mono); font-size:12.5px; letter-spacing:.04em; color:var(--ink-soft);}
nav.tabs{display:flex; align-items:center; gap:4px;}
.tab{font-family:var(--sans); font-size:14px; font-weight:600; color:var(--ink-soft); padding:8px 14px; border-radius:8px; border:none; background:transparent; cursor:pointer; transition:background .15s ease, color .15s ease;}
.tab:hover{color:var(--ink); background:var(--paper-raised);}
.tab.active{color:var(--ink); background:var(--paper-raised); box-shadow:inset 0 0 0 1px var(--line);}
.status-pill{display:flex; align-items:center; gap:7px; font-family:var(--mono); font-size:11.5px; color:var(--ink-soft); border:1px solid var(--line); background:var(--paper-raised); padding:6px 12px; border-radius:20px;}
.status-pill .dot{width:6px; height:6px; border-radius:50%; background:var(--green); animation:pulse 2s infinite;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(62,142,90,.45);} 70%{box-shadow:0 0 0 6px rgba(62,142,90,0);} 100%{box-shadow:0 0 0 0 rgba(62,142,90,0);}}

.doc-strip{font-family:var(--mono); font-size:11.5px; color:var(--ink-soft); border-bottom:1px solid var(--line); background:var(--paper-raised);}
.doc-strip .wrap{display:flex; gap:24px; flex-wrap:wrap; padding:7px 28px; max-width:1180px; margin:0 auto;}
.doc-strip span b{color:var(--ink); font-weight:600;}

.page{max-width:980px; margin:0 auto; padding:44px 28px 100px;}
.eyebrow{font-family:var(--mono); font-size:12.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--coral-dark); display:flex; align-items:center; gap:10px; margin-bottom:14px;}
.eyebrow::before{content:""; width:16px; height:2px; background:var(--coral); display:inline-block;}
.page h1{font-family:var(--serif); font-weight:600; font-size:clamp(26px,3.2vw,36px); margin:0 0 12px; letter-spacing:-0.01em;}
.page > p.lede{color:var(--ink-soft); font-size:16px; max-width:64ch; margin:0 0 36px;}

.toolbar{display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:20px;}
.collection-select-wrap{display:flex; align-items:center; gap:10px;}
.collection-select-wrap label{font-family:var(--mono); font-size:11.5px; color:var(--ink-soft); text-transform:uppercase; letter-spacing:.05em;}
select{font-family:var(--sans); font-size:14px; color:var(--ink); background:var(--paper-raised); border:1px solid var(--line); border-radius:6px; padding:8px 32px 8px 12px; appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%234A5251' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat:no-repeat; background-position:right 10px center; background-size:14px; cursor:pointer;}

.btn{display:inline-flex; align-items:center; gap:8px; font-family:var(--sans); font-weight:600; font-size:14.5px; padding:10px 18px; border-radius:8px; cursor:pointer; border:1px solid transparent; transition:transform .15s ease, background .15s ease, border-color .15s ease, opacity .15s ease;}
.btn:active{transform:translateY(1px);}
.btn:disabled{opacity:.5; cursor:not-allowed;}
.btn-primary{background:var(--coral); color:#fff;}
.btn-primary:hover:not(:disabled){background:var(--coral-dark);}
.btn-ghost{border-color:var(--line); color:var(--ink); background:var(--paper-raised);}
.btn-ghost:hover:not(:disabled){border-color:var(--ink);}
.btn svg{width:16px; height:16px;}

.add-panel{background:var(--paper-raised); border:1px solid var(--line); border-radius:10px; margin-bottom:0; overflow:hidden; max-height:0; opacity:0; transition:max-height .3s ease, opacity .3s ease;}
.add-panel.open{max-height:900px; opacity:1; margin-bottom:28px;}
.add-panel__inner{padding:24px;}
.dropzone{border:1.5px dashed var(--line); border-radius:8px; padding:36px 20px; text-align:center; cursor:pointer; transition:border-color .15s ease, background .15s ease;}
.dropzone:hover, .dropzone.drag-over{border-color:var(--coral); background:rgba(216,90,48,.04);}
.dropzone svg{width:26px; height:26px; color:var(--coral); margin-bottom:10px;}
.dropzone .dz-title{font-family:var(--sans); font-weight:600; font-size:15px; margin-bottom:4px;}
.dropzone .dz-sub{font-family:var(--mono); font-size:12px; color:var(--ink-soft);}

.pending-list{margin-top:18px; display:flex; flex-direction:column; gap:10px;}
.pending-item{background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:12px 14px;}
.pending-item__row{display:flex; align-items:center; gap:12px;}
.pending-item__icon{flex:0 0 auto; width:32px; height:32px; border-radius:6px; background:var(--navy); color:var(--coral); display:flex; align-items:center; justify-content:center; font-family:var(--mono); font-size:10px; font-weight:600;}
.pending-item__meta{flex:1 1 auto; min-width:0;}
.pending-item__name{font-size:14px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.pending-item__status{font-family:var(--mono); font-size:11px; color:var(--ink-soft); margin-top:2px;}
.pending-item__remove{flex:0 0 auto; width:24px; height:24px; border-radius:50%; border:none; background:transparent; color:var(--ink-soft); cursor:pointer; font-size:13px; display:flex; align-items:center; justify-content:center;}
.pending-item__remove:hover{background:var(--line); color:var(--ink);}
.progress-track{height:4px; background:var(--line); border-radius:2px; margin-top:10px; overflow:hidden;}
.progress-fill{height:100%; width:0%; background:var(--coral); border-radius:2px; transition:width .25s ease;}
.pending-item.done .progress-fill{background:var(--green);}
.pending-item.done .pending-item__icon{color:var(--green);}
.panel-actions{display:flex; justify-content:flex-end; gap:10px; margin-top:20px;}

.doc-table{width:100%; border-collapse:collapse;}
.doc-table thead th{text-align:left; font-family:var(--mono); font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--ink-soft); font-weight:500; padding:0 12px 10px; border-bottom:1px solid var(--line);}
.doc-table tbody tr{border-bottom:1px solid var(--line);}
.doc-table tbody tr:hover{background:var(--paper-raised);}
.doc-table td{padding:14px 12px; font-size:14px; vertical-align:middle;}
.doc-name{display:flex; align-items:center; gap:10px;}
.doc-name .file-ico{flex:0 0 auto; width:28px; height:28px; border-radius:6px; background:var(--navy); display:flex; align-items:center; justify-content:center; color:var(--coral); font-family:var(--mono); font-size:9px; font-weight:700;}
.doc-name .name-text{font-weight:600;}
.tag{font-family:var(--mono); font-size:11px; color:var(--ink-soft); background:var(--paper); border:1px solid var(--line); padding:3px 8px; border-radius:4px; white-space:nowrap;}
.row-action{background:transparent; border:none; color:var(--ink-soft); cursor:pointer; width:28px; height:28px; border-radius:6px; display:flex; align-items:center; justify-content:center;}
.row-action:hover{background:var(--paper); color:var(--red);}
.row-action svg{width:15px; height:15px;}
.empty-table{text-align:center; padding:48px 20px; color:var(--ink-soft); font-size:14px;}
.table-card{background:var(--paper-raised); border:1px solid var(--line); border-radius:10px; padding:8px 12px 4px; overflow-x:auto;}

footer{border-top:1px solid var(--line); padding:28px 0; margin-top:auto;}
.footer-row{display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px; max-width:1180px; margin:0 auto; padding:0 28px;}
.footer-meta{font-family:var(--mono); font-size:11.5px; color:var(--ink-soft);}

.chat-shell{flex:1 1 auto; display:flex; flex-direction:column; min-height:0; max-width:860px; width:100%; margin:0 auto; padding:0 24px;}
.chat-scroll{flex:1 1 auto; overflow-y:auto; padding:32px 0 16px; scroll-behavior:smooth;}
.empty-state{height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding-bottom:40px;}
.empty-state .mark{font-family:var(--mono); color:var(--coral); font-size:26px; margin-bottom:18px; letter-spacing:.1em;}
.empty-state h1{font-family:var(--serif); font-weight:600; font-size:clamp(24px,3vw,32px); margin:0 0 10px; letter-spacing:-0.01em;}
.empty-state p{color:var(--ink-soft); font-size:15px; max-width:44ch; margin:0 0 30px;}
.suggestion-grid{display:grid; grid-template-columns:1fr 1fr; gap:12px; width:100%; max-width:640px;}
@media (max-width:640px){ .suggestion-grid{grid-template-columns:1fr;} }
.suggestion{text-align:left; font-family:var(--sans); font-size:13.5px; color:var(--ink); background:var(--paper-raised); border:1px solid var(--line); border-radius:8px; padding:14px 16px; cursor:pointer; transition:border-color .15s ease, transform .15s ease;}
.suggestion:hover{border-color:var(--coral); transform:translateY(-1px);}
.suggestion .q-label{display:block; font-family:var(--mono); font-size:10.5px; text-transform:uppercase; letter-spacing:.06em; color:var(--coral-dark); margin-bottom:6px;}

.msg{display:flex; margin-bottom:28px; gap:14px;}
.msg.user{justify-content:flex-end;}
.msg.assistant{justify-content:flex-start; align-items:flex-start;}
.avatar{flex:0 0 auto; width:30px; height:30px; border-radius:6px; display:flex; align-items:center; justify-content:center; background:var(--navy); color:var(--coral); font-family:var(--mono); font-size:14px; font-weight:600; margin-top:2px;}
.bubble-user{max-width:75%; background:var(--paper-raised); border:1px solid var(--line); border-radius:12px 12px 2px 12px; padding:12px 16px; font-size:15px;}
.assistant-content{max-width:82%; font-size:15px;}
.assistant-content .status-line{display:flex; align-items:center; gap:9px; font-family:var(--mono); font-size:12px; color:var(--ink-soft); margin-bottom:10px;}
.assistant-content .status-line .dot{width:6px; height:6px; border-radius:50%; background:var(--green);}
.assistant-content .status-line.thinking .dot{background:var(--coral); animation:pulse 1.1s infinite; box-shadow:none;}
.assistant-content .answer-text{color:var(--ink); line-height:1.65; white-space:pre-wrap;}
.citation-row{display:flex; flex-wrap:wrap; gap:8px; margin-top:14px;}
.citation-chip{display:inline-flex; align-items:center; gap:6px; font-family:var(--mono); font-size:11.5px; color:var(--coral-dark); background:rgba(216,90,48,.08); border:1px solid rgba(216,90,48,.25); padding:5px 10px; border-radius:4px; cursor:default;}
.assistant-actions{display:flex; gap:6px; margin-top:12px;}
.icon-btn{display:flex; align-items:center; justify-content:center; width:28px; height:28px; border-radius:6px; border:1px solid transparent; background:transparent; color:var(--ink-soft); cursor:pointer; transition:background .15s ease, color .15s ease;}
.icon-btn:hover{background:var(--paper-raised); border-color:var(--line); color:var(--ink);}
.icon-btn svg{width:15px; height:15px;}

.composer-wrap{flex:0 0 auto; padding:14px 0 22px;}
.composer{display:flex; align-items:flex-end; gap:8px; background:var(--paper-raised); border:1px solid var(--line); border-radius:16px; padding:10px 10px 10px 14px; box-shadow:0 12px 32px -18px rgba(20,23,26,.25); transition:border-color .15s ease;}
.composer:focus-within{border-color:var(--coral);}
.composer textarea{flex:1 1 auto; border:none; background:transparent; resize:none; font-family:var(--sans); font-size:15px; color:var(--ink); line-height:1.5; padding:8px 4px; max-height:200px; min-height:24px;}
.composer textarea:focus{outline:none;}
.composer-btn{flex:0 0 auto; display:flex; align-items:center; justify-content:center; width:36px; height:36px; border-radius:10px; border:1px solid var(--line); background:var(--paper); color:var(--ink-soft); cursor:pointer; transition:background .15s ease, border-color .15s ease, color .15s ease;}
.composer-btn svg{width:17px; height:17px;}
.send-btn{border:none; background:var(--line); color:var(--paper-raised);}
.send-btn.active{background:var(--coral); color:#fff;}
.send-btn.active:hover{background:var(--coral-dark);}
.send-btn:disabled{cursor:not-allowed;}
.composer-hint{text-align:center; font-family:var(--mono); font-size:11px; color:var(--ink-soft); margin-top:10px;}

@media (max-width:720px){
  .doc-table thead{display:none;}
  .doc-table, .doc-table tbody, .doc-table tr, .doc-table td{display:block; width:100%;}
  .doc-table tr{padding:12px 0; border-bottom:1px solid var(--line);}
  .doc-table td{padding:4px 12px;}
}
`;

// ─── Root app ─────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView] = useState("query");
  const [docCount, setDocCount] = useState(0);

  useEffect(() => {
    apiFetch("/documents").then((d) => setDocCount(d.length)).catch(() => {});
  }, []);

  return (
    <>
      <style>{GLOBAL_STYLE}</style>
      <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
        <Header view={view} onSwitch={setView} />
        <DocStrip docCount={docCount} />
        <main style={{ flex: "1 1 auto", display: "flex", flexDirection: "column", minHeight: 0 }}>
          {view === "config"
            ? <ConfigView docCount={docCount} setDocCount={setDocCount} />
            : <QueryView />}
        </main>
        <Footer />
      </div>
    </>
  );
}
