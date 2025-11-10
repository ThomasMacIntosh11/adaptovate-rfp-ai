// frontend/src/App.jsx
import { useEffect, useMemo, useState } from "react";
import "./App.css";
import RFPCard from "./components/RFPCard.jsx";
import ProgressBar from "./components/ProgressBar.jsx";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const PAGE_SIZE = 100;

export default function App() {
  const [rfps, setRfps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  const [page, setPage] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [progress, setProgress] = useState({ total: 0, done: 0, stage: "" });

  const loadRfps = async (targetPage = page) => {
    try {
      setLoading(true);
      setError("");
      const offset = targetPage * PAGE_SIZE;
      const res = await fetch(`${API_BASE}/rfps?limit=${PAGE_SIZE}&offset=${offset}`);
      if (!res.ok) throw new Error(`GET /rfps ${res.status}`);
      const data = await res.json();
      const total = res.headers.get("X-Total-Count");
      if (total) setTotalCount(Number(total));
      setRfps(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error(e);
      setError("Could not load RFPs. Check backend.");
    } finally {
      setLoading(false);
    }
  };

  const refreshRfps = async () => {
    try {
      setRefreshing(true);
      setError("");
      const res = await fetch(`${API_BASE}/refresh`, { method: "POST" });
      let msg = "";
      try {
        const body = await res.json();
        msg = body?.message || "";
        if (body?.ok === false && body?.error) msg = `${msg} (${body.error})`;
      } catch { /* ignore */ }
      if (!res.ok) throw new Error(msg || `POST /refresh ${res.status}`);
      setPage(0);
      await loadRfps(0);
    } catch (e) {
      console.error(e);
      setError(e?.message || "Refresh failed. See browser console and backend logs.");
    } finally {
      setRefreshing(false);
    }
  };

  // Poll backend progress while refreshing
  useEffect(() => {
    if (!refreshing) return;
    let t = null;
    const tick = async () => {
      try {
        const r = await fetch(`${API_BASE}/progress`);
        if (r.ok) {
          const j = await r.json();
          setProgress(j || { total: 0, done: 0, stage: "" });
        }
      } catch { /* ignore */ }
      t = setTimeout(tick, 500);
    };
    tick();
    return () => { if (t) clearTimeout(t); };
  }, [refreshing]);

  // Reset progress when not refreshing
  useEffect(() => {
    if (!refreshing) setProgress({ total: 0, done: 0, stage: "" });
  }, [refreshing]);

  useEffect(() => { loadRfps(page); }, [page]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const active = rfps.filter((r) => {
      if (!r?.due_date) return true;
      const parsed = new Date(r.due_date);
      if (Number.isNaN(parsed.valueOf())) return true;
      return parsed >= today;
    });
    if (!term) return active;
    return active.filter((r) => {
      const hay = `${r?.title || ""} ${r?.summary || ""} ${r?.agency || ""}`.toLowerCase();
      return hay.includes(term);
    });
  }, [q, rfps]);

  const totalPages = Math.max(1, Math.ceil((totalCount || 0) / PAGE_SIZE));
  const goPrev = () => setPage((p) => Math.max(0, p - 1));
  const goNext = () => setPage((p) => ((p + 1) < totalPages ? p + 1 : p));

  const percent = (() => {
    const { total, done } = progress || {};
    if (!total || total <= 0) return 0;
    return Math.min(100, Math.max(0, Math.round((done / total) * 100)));
  })();

  return (
    <div className="app-wrap">
      <h1>ADAPTOVATE RFP Intelligence</h1>
      {refreshing && <ProgressBar percent={percent} label={progress?.stage || "Refreshing…"} />}

      <div className="actions">
        <button onClick={refreshRfps} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh RFPs"}
        </button>
        <button onClick={() => { setPage(0); loadRfps(0); }} disabled={loading || refreshing}>
          {loading ? "Loading…" : "Reload List"}
        </button>

        <input
          className="search"
          placeholder="Quick filter (title, summary, agency)…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div className="pagination">
        <button onClick={goPrev} disabled={page === 0 || loading || refreshing}>Previous</button>
        <span>Page {page + 1} of {totalPages}</span>
        <button onClick={goNext} disabled={loading || refreshing || page + 1 >= totalPages}>Next</button>
      </div>

      {error && (
        <div className="error">
          {error}
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <p className="empty">No RFPs yet. Click “Refresh RFPs” to fetch, or “Reload List” to re-sync.</p>
      )}

      <div className="list">
        {filtered.map((r) => (
          <RFPCard key={r.id ?? `${r.title}-${r.url}`} rfp={r} />
        ))}
      </div>

      <div className="pagination bottom">
        <button onClick={goPrev} disabled={page === 0 || loading || refreshing}>Previous</button>
        <span>Page {page + 1} of {totalPages}</span>
        <button onClick={goNext} disabled={loading || refreshing || page + 1 >= totalPages}>Next</button>
      </div>
    </div>
  );
}
