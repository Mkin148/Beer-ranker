"""
One-time migration: push your local multi-taster beers.db into Supabase.

Existing local ratings were credited to the taster 'Original'; they land in
Supabase under taster_email 'original@import.local'. Re-score under your own
Google identity any time from the app.

Setup:
    export SUPABASE_URL="https://xxxx.supabase.co"
    export SUPABASE_SERVICE_KEY="your-service-role-key"

Dry run first (prints what it would send, contacts nothing):
    python migrate_to_supabase.py --dry-run

Then for real:
    python migrate_to_supabase.py
"""

import os
import sqlite3
import sys

DB = os.environ.get("LOCAL_DB", "beers.db")
DIMS = ["packaging", "look", "smell", "taste", "drinkability"]


def read_local():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    beers = [dict(r) for r in con.execute("SELECT * FROM beers").fetchall()]
    ratings = [dict(r) for r in con.execute("SELECT * FROM ratings").fetchall()]
    con.close()
    return beers, ratings


def rating_payload(beer_id, r):
    taster = r.get("taster") or "Original"
    email = "original@import.local" if taster == "Original" else f"{taster}@import.local"
    return {
        "beer_id": beer_id, "taster_email": email, "taster_name": taster,
        "notes": r.get("notes"),
        **{k: r.get(k) for k in DIMS},
    }


def main(dry_run):
    beers, ratings = read_local()
    print(f"Read {len(beers)} beers and {len(ratings)} ratings from {DB}.")

    if dry_run:
        sample_b = {k: beers[0][k] for k in ("name", "style", "abv", "description")} \
            if beers else {}
        print("Would insert beers like:", sample_b)
        if ratings:
            print("Would insert ratings like:", rating_payload(999, ratings[0]))
        print("Dry run only — nothing sent.")
        return

    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    idmap = {}
    for b in beers:
        row = sb.table("beers").insert({
            "name": b["name"], "style": b.get("style"), "abv": b.get("abv"),
            "description": b.get("description"), "photo_url": None,
        }).execute().data
        idmap[b["id"]] = row[0]["id"]
    print(f"Inserted {len(idmap)} beers.")

    n = 0
    for r in ratings:
        new_id = idmap.get(r["beer_id"])
        if new_id is None:
            continue
        sb.table("ratings").upsert(
            rating_payload(new_id, r), on_conflict="beer_id,taster_email").execute()
        n += 1
    print(f"Inserted {n} ratings. Done.")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
