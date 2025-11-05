# backend/main.py
from pathlib import Path
from dotenv import load_dotenv
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env from the backend directory's parent (project root)
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

# Local imports
from .database import Base, engine, SessionLocal
from .models import RFP
from .ai_utils import summarize_rfp, score_rfp
from .rfp_scraper import scrape_real_rfps

# Create DB tables
Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="ADAPTOVATE RFP Intelligence", version="1.0.0")

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Health / Debug ----------

@app.get("/")
def root():
    return {"ok": True, "service": "ADAPTOVATE RFP Intelligence"}

@app.get("/health")
def health():
    return {"status": "up"}

# ---------- Primary endpoints ----------

@app.get("/rfps")
def get_rfps():
    """
    Return RFPs as plain JSON (not ORM objects) so the frontend always
    receives a clean array even if Pydantic models aren’t defined.
    """
    db = SessionLocal()
    try:
        rows = db.query(RFP).order_by(RFP.score.desc().nullslast()).all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "url": r.url,
                "agency": r.agency,
                "category": r.category,
                "summary": r.summary,
                "score": r.score,
            }
            for r in rows
        ]
    finally:
        db.close()


@app.post("/refresh")
def refresh_rfps():
    """
    SAFER REFRESH:
    - Fetch all new items first (no DB changes yet).
    - If none were fetched, keep existing rows.
    - If some were fetched, replace the table contents.
    - Per-item AI failures no longer nuke the batch.
    - Returns counts + a few error samples for visibility.
    """
    import traceback
    db = SessionLocal()
    errors = []

    try:
        # 1) Fetch items from sources (no DB changes yet)
        try:
            items = scrape_real_rfps()
        except Exception as e:
            existing_count = db.query(RFP).count()
            return {
                "message": f"Scrape failed; keeping existing {existing_count} rows.",
                "error": f"{type(e).__name__}: {e}",
            }

        if not items:
            existing_count = db.query(RFP).count()
            return {"message": f"No new items fetched; keeping existing {existing_count} rows."}

        # 2) Prepare summaries/scores in memory with per-item protection
        criteria = os.getenv(
            "FILTER_KEYWORDS",
            "management consulting, agile transformation, digital strategy",
        )
        prepared = []
        for i, r in enumerate(items, start=1):
            title = r.get("title") or "Untitled"
            desc = r.get("description") or ""
            agency = r.get("agency") or ""
            url = r.get("url") or ""
            category = r.get("category") or "Opportunity"

            text = f"{title}\n\n{desc}\n\nAgency: {agency}"

            try:
                summary = summarize_rfp(text)
            except Exception as e:
                errors.append(f"summary item {i}: {type(e).__name__}: {e}")
                summary = "Summary unavailable."

            try:
                score = float(score_rfp(text, criteria))
            except Exception as e:
                errors.append(f"score item {i}: {type(e).__name__}: {e}")
                score = 0.0

            prepared.append(
                RFP(
                    title=title,
                    description=desc,
                    url=url,
                    agency=agency,
                    category=category,
                    summary=summary,
                    score=score,
                )
            )

        # 3) Swap data in one transaction
        try:
            db.begin()
            db.query(RFP).delete()
            db.add_all(prepared)
            db.commit()
        except Exception as e:
            db.rollback()
            existing_count = db.query(RFP).count()
            return {
                "message": f"DB write failed; kept existing {existing_count} rows.",
                "error": f"{type(e).__name__}: {e}",
            }

        return {
            "message": f"Ingested {len(prepared)} notices.",
            "errors": errors[:5],
        }

    except Exception as e:
        db.rollback()
        return {
            "message": f"refresh failed: {type(e).__name__}: {e}",
            "trace": traceback.format_exc().splitlines()[-8:],
        }
    finally:
        db.close()


@app.post("/debug/seed")
def debug_seed():
    """Insert two sample rows to prove the UI/DB wiring without external calls."""
    db = SessionLocal()
    try:
        db.query(RFP).delete()
        db.add_all([
            RFP(
                title="AI Strategy Consulting – Pilot",
                description="Type: Solicitation | NAICS: 541611 | PSC: R499",
                url="https://example.com/rfp1",
                agency="Dept. Example A",
                category="Opportunity",
                summary="Agency seeks partner to deliver AI roadmap, governance, and MVP pilot.",
                score=88.5,
            ),
            RFP(
                title="Enterprise Agile Transformation",
                description="Type: Tender | NAICS: 541612 | PSC: D399",
                url="https://example.com/rfp2",
                agency="Dept. Example B",
                category="Tender",
                summary="Org requires enterprise agile coaching, tooling rollout, and training.",
                score=76.2,
            ),
        ])
        db.commit()
        return {"message": "Seeded 2 sample RFPs"}
    finally:
        db.close()