// frontend/src/App.jsx
import { useEffect, useState } from "react";
import { getRFPs, refreshRFPs } from "./api";
import RFPCard from "./components/RFPCard";

export default function App() {
  const [rfps, setRfps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadRfps = async () => {
    try {
      setLoading(true);
      setError("");
      const { data } = await getRFPs();
      setRfps(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("GET /rfps failed:", e);
      setError("Could not load RFPs. Check backend logs and API_URL.");
    } finally {
      setLoading(false);
    }
  };

  const refresh = async () => {
    try {
      setRefreshing(true);
      setError("");
      const { data } = await refreshRFPs();
      console.log("Refresh response:", data);
      await loadRfps();
    } catch (e) {
      console.error("POST /refresh failed:", e);
      setError("Refresh failed. See console and backend logs.");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadRfps();
  }, []);

  return (
    <div className="p-6">
      <h1 className="text-4xl font-extrabold mb-6">ADAPTOVATE RFP Intelligence</h1>

      <div className="space-x-3">
        <button
          onClick={refresh}
          disabled={refreshing}
          className="bg-gray-100 hover:bg-gray-200 text-gray-800 px-4 py-2 rounded shadow"
        >
          {refreshing ? "Refreshing..." : "Refresh RFPs"}
        </button>

        <button
          onClick={loadRfps}
          className="bg-gray-100 hover:bg-gray-200 text-gray-800 px-4 py-2 rounded shadow"
        >
          Reload List
        </button>
      </div>

      {loading && <p className="mt-4">Loading RFPs…</p>}
      {error && <p className="mt-4 text-red-600">{error}</p>}
      {!loading && !error && rfps.length === 0 && (
        <p className="mt-6 text-gray-500">No RFPs yet. Click “Refresh RFPs” or run the debug seed (see step below).</p>
      )}

      <div className="mt-6 space-y-3">
        {rfps.map((r) => (
          <RFPCard key={r.id ?? `${r.title}-${r.url}`} rfp={r} />
        ))}
      </div>
    </div>
  );
}