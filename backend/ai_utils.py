# backend/ai_utils.py
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load the .env that lives in backend/ (works even when uvicorn runs from project root)
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

def _get_client() -> OpenAI:
    """
    Lazily construct an OpenAI client using OPENAI_API_KEY from env.
    This avoids failing at import time if the key hasn't been loaded yet.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Put it in backend/.env or export it in your shell."
        )
    return OpenAI(api_key=api_key)

def summarize_rfp(text: str) -> str:
    """Return a concise 5-sentence summary for consulting partners."""
    client = _get_client()
    prompt = (
        "Summarize the following RFP for management/AI consulting partners in 5 short sentences. "
        "Include: client/agency, problem, scope, key requirements, dates if present. "
        "Keep it crisp and executive-ready.\n\n"
        f"{text}"
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

def score_rfp(text: str, criteria: str) -> float:
    """Return a numeric relevance score 0–100 based on criteria."""
    client = _get_client()
    prompt = (
        "You are a bid/no-bid triage assistant. "
        "Rate how well this RFP matches the firm's target work using ONLY a number 0-100.\n\n"
        f"Target criteria: {criteria}\n\n"
        f"RFP text:\n{text}\n\n"
        "Return just the number."
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = resp.choices[0].message.content.strip()
    try:
        import re
        m = re.search(r"\d+(\.\d+)?", raw)
        return float(m.group(0)) if m else 0.0
    except Exception:
        return 0.0