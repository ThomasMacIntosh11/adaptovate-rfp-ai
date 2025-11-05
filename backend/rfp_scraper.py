def scrape_real_rfps() -> list[dict[str, any]]:
    """
    Fetch CanadaBuys tenders and filter by keywords defined in .env.
    """
    import os
    from .rfp_sources_canadabuys import fetch_canadabuys_tenders

    # Load and normalize keywords from .env (comma-separated)
    raw = os.getenv("FILTER_KEYWORDS", "")
    keywords = [kw.strip().lower() for kw in raw.split(",") if kw.strip()]
    print(f"[INFO] Applying keyword filters: {keywords if keywords else '(none)'}")

    try:
        all_items = fetch_canadabuys_tenders(max_rows=2000)
    except Exception as e:
        print(f"[WARN] CanadaBuys fetch failed: {type(e).__name__}: {e}")
        return []

    print(f"[INFO] Retrieved {len(all_items)} total CanadaBuys tenders")

    if not keywords:
        print("[INFO] No keywords defined — returning all tenders.")
        return all_items

    # Filter by keyword appearing in title or description (case-insensitive)
    filtered = []
    for item in all_items:
        hay = (item.get("title", "") + " " + item.get("description", "")).lower()
        if any(kw in hay for kw in keywords):
            filtered.append(item)

    print(f"[INFO] Filtered down to {len(filtered)} tenders matching keywords.")
    return filtered