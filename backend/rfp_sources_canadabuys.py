# backend/rfp_sources_canadabuys.py
import io
import requests
import pandas as pd
from typing import List, Dict, Any

CSV_URL = "https://canadabuys.canada.ca/opendata/pub/newTenderNotice-nouvelAvisAppelOffres.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
    "Accept": "text/csv,application/json;q=0.9,*/*;q=0.8",
}

def fetch_canadabuys_tenders(max_rows: int = 2000) -> List[Dict[str, Any]]:
    """Fetch and normalize tender data from CanadaBuys open data CSV."""
    r = requests.get(CSV_URL, headers=HEADERS, timeout=90)
    r.raise_for_status()

    df = pd.read_csv(io.BytesIO(r.content), encoding="utf-8-sig", low_memory=False)

    # Use exact known columns
    title_col = "title-titre-eng"
    url_col = "noticeURL-URLavis-eng"
    org_col = "contractingEntityName-nomEntitContractante-eng"
    date_col = "publicationDate-datePublication"
    type_col = "noticeType-avisType-eng"

    results = []
    for _, row in df.head(max_rows).iterrows():
        title = str(row.get(title_col, "")).strip()
        url = str(row.get(url_col, "")).strip()
        org = str(row.get(org_col, "")).strip()
        posted = str(row.get(date_col, "")).strip()
        ntype = str(row.get(type_col, "")).strip()

        if not title or not url:
            continue

        results.append({
            "source": "CanadaBuys",
            "title": title,
            "description": f"Type: {ntype or 'Tender'}",
            "url": url,
            "agency": org,
            "category": ntype or "Tender",
            "posted_date": posted,
        })

    return results