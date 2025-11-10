// frontend/src/components/RFPCard.jsx
const formatPostedDate = (value) => {
  if (!value) return "";
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.valueOf())) {
    return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }
  return String(value).split("T")[0];
};

export default function RFPCard({ rfp }) {
  const title = rfp?.title || "Untitled";
  const agency = rfp?.agency || "";
  const url = rfp?.url || "";
  const score = typeof rfp?.score === "number" ? `${rfp.score.toFixed(1)}%` : "—";
  const posted = formatPostedDate(rfp?.posted_date);
  const tags = (Array.isArray(rfp?.focus_tags) && rfp.focus_tags.length ? rfp.focus_tags : ["Consulting"]).slice(0, 3);

  const onClick = () => {
    if (url && /^https?:\/\//i.test(url)) {
      window.open(url, "_blank", "noopener,noreferrer");
    } else {
      alert("Pending URL");
    }
  };

  return (
    <div className="card">
      <h3 className="card-title">{title}</h3>
      {agency ? <div className="card-agency">{agency}</div> : null}

      <div className="card-tags">
        {tags.map((tag) => (
          <span key={tag} className="card-pill">{tag}</span>
        ))}
      </div>

      <div className="card-meta">
        <div className="meta-block">
          <span className="meta-label">Relevance</span>
          <span className="meta-value">{score}</span>
        </div>
        <div className="meta-block">
          <span className="meta-label">Posted</span>
          <span className="meta-value">{posted || "—"}</span>
        </div>
      </div>

      <div className="card-actions">
        <button onClick={onClick} className={url ? "primary" : "muted"}>
          {url ? "View RFP" : "Pending URL"}
        </button>
      </div>
    </div>
  );
}
