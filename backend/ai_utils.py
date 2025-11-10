# backend/ai_utils.py
import os
from typing import Dict
from dotenv import load_dotenv

try:
    from openai import OpenAI
except Exception:
    from openai import OpenAI  # fallback

# Always load backend/.env no matter where uvicorn is started from
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _get_client() -> OpenAI:
    """
    Lazy-init OpenAI client so we don't require OPENAI_API_KEY at import time.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key.lower() == "none":
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Update backend/.env or export it in your shell."
        )
    return OpenAI(api_key=api_key)

def summarize_rfp(rfp_text: str) -> str:
    """Return a single-sentence plain-language summary for the card UI."""
    client = _get_client()
    prompt = (
        "You are an expert proposal analyst for ADAPTOVATE. "
        "Write exactly ONE sentence (<=30 words) that captures the buyer, goal, and key workstream of this RFP. "
        "Avoid jargon, no bullet points, no introductions like 'This RFP...'." \
        "\n\n"
        f"RFP TEXT:\n{rfp_text}\n"
    )
    try:
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": "You are a concise executive analyst."},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.output_text if hasattr(resp, "output_text") else ""
        if not content and hasattr(resp, "choices"):
            content = resp.choices[0].message.content
        return (content or "").strip()
    except Exception as e:
        return f"(summary unavailable: {type(e).__name__}: {e})"

def score_relevance(rfp_text: str) -> Dict[str, int]:
    """
    Return {'score': 0..100, 'rationale': '...'} for fit to ADAPTOVATE focus (AI, Agile, Transformation).
    """
    client = _get_client()
    prompt = (
        "Score how well this opportunity fits a consulting firm focused on: "
        "AI (including GenAI), agile coaching, transformations, product & digital strategy, "
        "and change management. Consider whether it is services (not commodities), "
        "government/public sector alignment, and clarity of scope. Return ONLY a JSON object "
        "with fields: score (0-100 integer) and rationale (short string).\n\n"
        f"TEXT:\n{rfp_text}\n"
    )
    try:
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": "You are a disciplined evaluator. Output JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = resp.output_text if hasattr(resp, "output_text") else ""
        if not raw and hasattr(resp, "choices"):
            raw = resp.choices[0].message.content or ""

        import json, re
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {"score": 0, "rationale": "No JSON found from model output."}
        data = json.loads(m.group(0))
        sc = int(data.get("score", 0))
        sc = max(0, min(100, sc))
        return {"score": sc, "rationale": str(data.get("rationale", ""))[:400]}
    except Exception as e:
        return {"score": 0, "rationale": f"model error: {type(e).__name__}: {e}"}
