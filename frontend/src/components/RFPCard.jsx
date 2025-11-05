// frontend/src/components/RFPCard.jsx
export default function RFPCard({ rfp }) {
  return (
    <div className="border rounded p-4 shadow-sm">
      <h2 className="font-bold text-lg">{rfp.title}</h2>
      {rfp.agency && <p className="text-sm italic">{rfp.agency}</p>}
      {rfp.summary && <p className="mt-2">{rfp.summary}</p>}
      <div className="flex items-center justify-between mt-3">
        <p className="text-sm">Relevance Score: {Number(rfp.score ?? 0).toFixed(1)}%</p>
        <a
          href={rfp.url}
          target="_blank"
          rel="noreferrer"
          className="text-blue-600 underline"
        >
          View RFP
        </a>
      </div>
    </div>
  );
}