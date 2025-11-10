# backend/main.py
import os
import re
import sqlite3
from datetime import datetime, date
from typing import List, Optional

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from .rfp_scraper import scrape_real_rfps
from .relevance import compute_rule_score
from .ai_utils import summarize_rfp, score_relevance

# Always load env from backend folder
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# Focus areas derived from env priority terms
def _env_list(name: str) -> List[str]:
    raw = os.getenv(name, "") or ""
    return [t.strip() for t in raw.split(",") if t.strip()]

def _compile_focus_pattern(term: str):
    slug = " ".join((term or "").lower().split())
    if not slug:
        return None
    escaped = re.escape(slug).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)

def _format_tag_label(term: str) -> str:
    cleaned = (term or "").strip()
    if not cleaned:
        return ""
    tokens = cleaned.split()
    formatted = []
    for tok in tokens:
        if len(tok) <= 3:
            formatted.append(tok.upper())
        else:
            formatted.append(tok[0].upper() + tok[1:])
    return " ".join(formatted)

def _load_focus_terms():
    seen = set()
    ordered = []
    for env_name in ("AI_PRIORITY_TERMS", "POSITIVE_BOOST_TERMS"):
        for item in _env_list(env_name):
            slug = " ".join(item.lower().split())
            if not slug or slug in seen:
                continue
            pattern = _compile_focus_pattern(item)
            if not pattern:
                continue
            seen.add(slug)
            ordered.append({
                "needle": slug,
                "label": _format_tag_label(item),
                "pattern": pattern,
            })
    return ordered

FOCUS_TERMS = _load_focus_terms()

PILL_KEYWORDS = [
    ("AI", [
        "ai", "artificial intelligence", "generative ai", "genai", "machine learning",
        "chatbot", "chatbots", "conversational ai", "automation", "llm",
    ]),
    ("Operating Model", [
        "operating model", "target operating model", "tom", "operating-model",
    ]),
    ("Transformation", [
        "transformation", "transformational", "modernization", "change program",
    ]),
    ("Culture", [
        "culture", "cultural", "mindset", "behaviour change",
    ]),
    ("Strategy", [
        "strategy", "strategic", "roadmap", "vision", "plan",
    ]),
    ("Process", [
        "process", "processes", "process improvement", "process optimization",
        "business process", "workflow",
    ]),
]

def _extract_focus_tags(text: str, limit: int = 3) -> List[str]:
    if not text:
        return []
    hay = text.lower()
    tags: List[str] = []
    for label, keywords in PILL_KEYWORDS:
        if any(kw in hay for kw in keywords):
            tags.append(label)
        if len(tags) >= limit:
            break
    if not tags:
        tags.append("Strategy")
    return tags[:limit]

def _text_has_focus_signal(text: str) -> bool:
    if not text or not FOCUS_TERMS:
        return False
    for term in FOCUS_TERMS:
        pattern = term.get("pattern")
        if pattern and pattern.search(text):
            return True
    return False

def _normalize_iso_date(value: str) -> str:
    if not value:
        return ""
    v = value.strip()
    if not v:
        return ""
    fmts = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(v[:len(fmt)], fmt)
            return dt.date().isoformat()
        except ValueError:
            continue
    try:
        cleaned = v[:-1] + "+00:00" if v.endswith("Z") else v
        dt = datetime.fromisoformat(cleaned)
        return dt.date().isoformat()
    except ValueError:
        return v[:10] if len(v) >= 10 else v

def _format_posted_date(value: str) -> str:
    return _normalize_iso_date(value)

def _format_due_date(value: str) -> str:
    return _normalize_iso_date(value)

def _iso_to_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None

# --- progress tracking (in-memory) ---
from threading import Lock
PROGRESS = {"total": 0, "done": 0, "stage": ""}
PROGRESS_LOCK = Lock()
SCHEMA_LOCK = Lock()
SCHEMA_READY = False

def _set_progress(total: int = None, done: int = None, stage: str = None):
    with PROGRESS_LOCK:
        if total is not None:
            PROGRESS["total"] = int(total)
        if done is not None:
            PROGRESS["done"] = int(done)
        if stage is not None:
            PROGRESS["stage"] = stage

app = FastAPI(title="ADAPTOVATE RFP Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "rfps.db"))

def _ensure_schema(conn: sqlite3.Connection):
    global SCHEMA_READY
    if SCHEMA_READY:
        return
    with SCHEMA_LOCK:
        if SCHEMA_READY:
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rfps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                agency TEXT,
                summary TEXT,
                description TEXT,
                url TEXT,
                score REAL,
                posted_date TEXT,
                due_date TEXT,
                created_at TEXT,
                dedupe_key TEXT NOT NULL DEFAULT ''
            )
            """
        )
        try:
            conn.execute("ALTER TABLE rfps ADD COLUMN dedupe_key TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE rfps ADD COLUMN due_date TEXT")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            UPDATE rfps
            SET dedupe_key = CASE
                WHEN TRIM(IFNULL(title, '')) = '' AND TRIM(IFNULL(agency, '')) = '' AND TRIM(IFNULL(posted_date, '')) = ''
                    THEN 'rfp_' || id
                ELSE TRIM(IFNULL(title, '')) || '|' || TRIM(IFNULL(agency, '')) || '|' || TRIM(IFNULL(posted_date, ''))
            END
            WHERE dedupe_key IS NULL OR TRIM(dedupe_key) = ''
            """
        )
        conn.execute("DROP INDEX IF EXISTS idx_rfps_dedupe_key")
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_rfps_dedupe_key
            ON rfps(dedupe_key)
            """
        )
        conn.commit()
        SCHEMA_READY = True

def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn

class RefreshResponse(BaseModel):
    message: str
    errors: List[str] = []

@app.get("/progress")
def get_progress():
    with PROGRESS_LOCK:
        return dict(PROGRESS)

@app.get("/rfps")
def list_rfps(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    q: str = Query("", description="optional search over title/summary/agency"),
    response: Response = None,
):
    conn = _conn()
    cur = conn.cursor()
    due_clause = "(due_date IS NULL OR due_date = '' OR date(due_date) >= date('now'))"

    # total count (for pagination header)
    if q.strip():
        like = f"%{q.strip()}%"
        cur.execute(
            f"SELECT COUNT(*) FROM rfps WHERE {due_clause} AND (title LIKE ? OR summary LIKE ? OR agency LIKE ?)",
            (like, like, like),
        )
    else:
        cur.execute(f"SELECT COUNT(*) FROM rfps WHERE {due_clause}")
    total = int(cur.fetchone()[0])
    if response is not None:
        response.headers["X-Total-Count"] = str(total)

    if q.strip():
        like = f"%{q.strip()}%"
        cur.execute(
            f"""
            SELECT id, title, agency, summary, description, url, score, posted_date, due_date, created_at
            FROM rfps
            WHERE {due_clause} AND (title LIKE ? OR summary LIKE ? OR agency LIKE ?)
            ORDER BY score DESC, datetime(created_at) DESC
            LIMIT ? OFFSET ?
            """,
            (like, like, like, limit, offset),
        )
    else:
        cur.execute(
            f"""
            SELECT id, title, agency, summary, description, url, score, posted_date, due_date, created_at
            FROM rfps
            WHERE {due_clause}
            ORDER BY score DESC, datetime(created_at) DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        row["posted_date"] = _format_posted_date(row.get("posted_date", ""))
        row["due_date"] = _format_due_date(row.get("due_date", ""))
        haystack = " ".join([
            row.get("title", ""),
            row.get("summary", ""),
            row.get("description", ""),
            row.get("agency", ""),
        ])
        row["focus_tags"] = _extract_focus_tags(haystack)
    conn.close()
    return rows

@app.post("/refresh", response_model=RefreshResponse)
def refresh_rfps(limit: int = 300, no_ai: bool = False):
    """
    Workflow:
      1) Scrape CanadaBuys (CSV only, includes UNSPSC when present)
      2) UNSPSC filter (FILTER_UNSPSC)
      3) Keyword filter (FILTER_KEYWORDS)
      4) Score + (optional) AI summary; insert into DB
      Progress updates during ingest.
    """
    _set_progress(total=0, done=0, stage="fetching")
    errors: List[str] = []

    try:
        items = scrape_real_rfps(limit=int(limit))
    except Exception as e:
        errors.append(f"scrape: {type(e).__name__}: {e}")
        items = []

    _set_progress(total=len(items), done=0, stage="ingesting")

    AI_TOP_N = int(os.getenv("AI_TOP_N", "30"))
    ALPHA = float(os.getenv("RELEVANCE_ALPHA", "0.6"))
    MIN_RULE_SCORE = float(os.getenv("MIN_RULE_SCORE", "40"))

    def _dedupe_key(title: str, agency: str, posted_date: str) -> str:
        t = (title or "").strip() or "(untitled)"
        a = (agency or "").strip() or "(agency)"
        p = (posted_date or "").strip() or "(date)"
        return f"{t}|{a}|{p}"

    def _upsert(row: dict):
        conn = _conn()
        cur = conn.cursor()
        title = (row.get("title") or "").strip()
        agency = (row.get("agency") or "").strip()
        summary = row.get("summary", "")
        description = row.get("description", "")
        posted_date = (row.get("posted_date") or "").strip()
        posted_date = _format_posted_date(posted_date)
        url_raw = (row.get("url") or "").strip()
        url_value = url_raw if url_raw else None
        score = float(row.get("score", 0.0))
        dedupe_key = _dedupe_key(title, agency, posted_date)
        created_at = datetime.utcnow().isoformat(timespec="seconds")

        cur.execute(
            """
            INSERT INTO rfps(title, agency, summary, description, url, score, posted_date, created_at, dedupe_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                title=excluded.title,
                agency=excluded.agency,
                summary=excluded.summary,
                description=excluded.description,
                url=COALESCE(excluded.url, rfps.url),
                score=excluded.score,
                posted_date=excluded.posted_date
            """,
            (
                title,
                agency,
                summary,
                description,
                url_value,
                score,
                posted_date,
                created_at,
                dedupe_key,
            ),
        )
        conn.commit()
        conn.close()

    # Base rule score
    for it in items:
        it["_rule_score"] = compute_rule_score(it)

    def _hay_for_item(it: dict) -> str:
        return " ".join([
            it.get("title") or "",
            it.get("description") or "",
            it.get("agency") or "",
            it.get("category") or "",
        ])

    filtered_items = []
    for it in items:
        hay = _hay_for_item(it)
        if it["_rule_score"] >= MIN_RULE_SCORE or _text_has_focus_signal(hay):
            filtered_items.append(it)
    if len(filtered_items) != len(items):
        print(f"[FILTER] Dropped {len(items) - len(filtered_items)} items below MIN_RULE_SCORE={MIN_RULE_SCORE}")
    items = filtered_items

    # Select AI targets
    ai_targets = [] if no_ai else sorted(items, key=lambda x: x["_rule_score"], reverse=True)[:AI_TOP_N]
    ai_ids = {id(o) for o in ai_targets}

    ingested = 0
    for idx, it in enumerate(items, start=1):
        try:
            title = (it.get("title") or "").strip()
            agency = (it.get("agency") or "").strip()
            description = (it.get("description") or "").strip()
            posted_date = (it.get("posted_date") or "").strip()
            url = (it.get("url") or "").strip()

            rfp_text = f"{title}\n\nAgency: {agency}\n\n{description}\n\nURL: {url or '(pending)'}\nPosted: {posted_date}"

            rule_score = float(it.get("_rule_score", 0.0))
            ai_score = 0.0
            summary = ""

            if not no_ai and id(it) in ai_ids:
                try:
                    sd = score_relevance(rfp_text)
                    ai_score = float(sd.get("score", 0))
                    summary = summarize_rfp(rfp_text)
                except Exception as e:
                    errors.append(f"ai item {idx}: {type(e).__name__}: {e}")
                    ai_score = 0.0
                    summary = ""

            final_score = rule_score if no_ai else (ALPHA * rule_score + (1 - ALPHA) * ai_score)
            row = {
                "title": title,
                "agency": agency,
                "summary": summary,
                "description": description,
                "url": url,
                "score": float(round(final_score, 1)),
                "posted_date": posted_date,
            }
            _upsert(row)
            ingested += 1
        except Exception as e:
            errors.append(f"ingest item {idx}: {type(e).__name__}: {e}")
        finally:
            _set_progress(done=idx)

    _set_progress(stage="done")
    return RefreshResponse(message=f"Ingested {ingested} notices.", errors=errors)
