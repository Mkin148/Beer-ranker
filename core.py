"""
Pure logic for Beer Ranker — no Streamlit, no network. Kept separate so the
scoring/aggregation can be unit-tested offline.
"""

import io
import re

import numpy as np
import pandas as pd

DIM_KEYS = ["packaging", "look", "smell", "taste", "drinkability"]
LABELS = {
    "packaging": "Packaging Presentation",
    "look": "Look",
    "smell": "Smell",
    "taste": "Taste",
    "drinkability": "Drinkability",
}
SCALE_MAX = 5.0


def parse_abv(text):
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(text))
    return float(m.group(1)) if m else None


def build_leaderboard(beers, ratings):
    """
    beers:   list of dicts (id, name, style, abv, description, photo_url)
    ratings: list of dicts (beer_id, taster_email, taster_name, <5 dims>, notes)
    Returns one row per beer with per-dimension averages across tasters,
    n_raters, total (/25) and avg (/5). Unrated beers get NaN dims, n_raters 0.
    """
    bdf = pd.DataFrame(beers)
    if bdf.empty:
        return bdf
    bdf = bdf.rename(columns={"id": "beer_id"})

    rdf = pd.DataFrame(ratings)
    if rdf.empty:
        for k in DIM_KEYS:
            bdf[k] = np.nan
        bdf["n_raters"] = 0
    else:
        for k in DIM_KEYS:
            rdf[k] = pd.to_numeric(rdf[k], errors="coerce")  # numeric may arrive as str
        agg = rdf.groupby("beer_id").agg(
            n_raters=("taster_email", "nunique"),
            **{k: (k, "mean") for k in DIM_KEYS},
        ).reset_index()
        bdf = bdf.merge(agg, on="beer_id", how="left")
        bdf["n_raters"] = bdf["n_raters"].fillna(0).astype(int)

    if "abv" in bdf:
        bdf["abv"] = pd.to_numeric(bdf["abv"], errors="coerce")
    bdf["total"] = bdf[DIM_KEYS].sum(axis=1, min_count=len(DIM_KEYS))
    bdf["avg"] = bdf["total"] / len(DIM_KEYS)
    return bdf


def process_image(file, max_side=900):
    """Downscale + re-encode to a small JPEG (bytes)."""
    from PIL import Image
    img = Image.open(file).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def star_html(avg, size=20):
    pct = 0 if avg is None or pd.isna(avg) else max(0.0, min(100.0, avg / SCALE_MAX * 100))
    return (
        f"<span style='display:inline-block;position:relative;font-size:{size}px;"
        f"line-height:1;letter-spacing:2px;'>"
        f"<span style='color:#e3e3e3;'>★★★★★</span>"
        f"<span style='color:#f5a623;position:absolute;left:0;top:0;overflow:hidden;"
        f"white-space:nowrap;width:{pct}%;'>★★★★★</span></span>"
    )
