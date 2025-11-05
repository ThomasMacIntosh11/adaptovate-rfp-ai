# backend/rfp_scraper.py
import os
from typing import List, Dict, Any

from .rfp_sources_canadabuys import fetch_canadabuys_tenders

def _env_list(name: str) -> List[str]:
    val = os.getenv(name, "") or ""
    return [v.strip() for v in val.split(",") if v.strip()]

def scrape_real_rfps() -> List[Dict[str, Any]]:
    """
    Temporarily skip SAM.gov (rate-limited) and fetch only CanadaBuys tenders.
    This guarantees real data flow while SAM rate limits reset or until we
    re-enable SAM with a lower request profile.
    """
    canada_items = []
    try:
        canada_items = fetch_canadabuys_tenders(max_rows=1000)
    except Exception as e:
        print(f"[WARN] CanadaBuys fetch failed: {type(e).__name__}: {e}")

    return canada_items