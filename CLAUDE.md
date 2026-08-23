# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Meet and Drink** — a small **Streamlit** web app where a private group ranks
beers. Each taster scores a beer on five dimensions (each out of 5); a beer's
rank is the **average across all tasters**. Live at `beerranker.streamlit.app`
(the app's display name has changed but the Streamlit Cloud subdomain has
not — renaming it is a separate step, see Gotchas).

## Stack

- **Streamlit** — UI, deployed on **Streamlit Community Cloud** (auto-redeploys
  from the `main` branch on GitHub).
- **Supabase** — Postgres holds `beers` and `ratings`; a public Storage bucket
  (`beer-photos`) holds photos. Accessed via the `supabase` Python client using
  the **service_role key** (server-side only), which bypasses RLS.
- **Google login** via Streamlit's native `st.login` (OIDC). The logged-in
  Google account is the taster identity.

## Commands

```bash
pip install -r requirements.txt          # install deps
streamlit run app.py                     # run locally at localhost:8501
python migrate_to_supabase.py --dry-run  # preview one-off SQLite -> Supabase import
python migrate_to_supabase.py            # run it for real (never twice — see Gotchas)
```

Local runs need `.streamlit/secrets.toml` filled in (copy from
`secrets.toml.example`) — see `DEPLOY.md` for the full first-time setup.
There is no lint config or test suite in this repo.

## Files

- `app.py` — all UI + Supabase/auth wiring. Everything user-facing lives here.
- `core.py` — **pure logic** (no Streamlit, no network): scoring constants,
  `build_leaderboard()`, `process_image()`, `star_html()`. Unit-testable
  offline. Put logic here, not in `app.py`, when practical.
- `schema.sql` — Supabase table definitions. Run once in the Supabase SQL editor.
- `migrate_to_supabase.py` — one-off import from a local SQLite `beers.db` into
  Supabase. Auto-detects the old single-player schema vs the multi-taster one.
- `requirements.txt` — deps (streamlit, Authlib, supabase, pandas, numpy,
  altair, pillow).
- `.streamlit/secrets.toml` — real secrets. **Gitignored — never commit.**
- `.streamlit/secrets.toml.example` — template (safe to commit).
- `DEPLOY.md` — full first-time deployment guide (Supabase, Google, deploy).

## Data model

- `beers`: id, name, style, origin, abv, description, photo_url, created_at.
  Added via the Add beer tab with no score attached — it's rated separately
  from the Rate beers tab.
- `ratings`: id, beer_id (FK, ON DELETE CASCADE), taster_email, taster_name,
  five score columns, notes, created_at. `UNIQUE(beer_id, taster_email)` — one
  rating per taster per beer, updated via upsert.
- The five dimensions (DB column names): `packaging, look, smell, taste,
  drinkability`. Display labels are in `core.py` `LABELS`
  (packaging → "Packaging Presentation"). Display order = `DIM_KEYS` order.

## Access model (current)

- **Public (no login):** Browse only — it's the leaderboard and photo browser
  merged into one view (podium + ranked list; click a beer to see its full
  score breakdown), so it's enough for someone who just wants to see the
  site. A "Log in to join the beer magic" button sits above the tabs.
- **Login required:** Rate beers.
- **Admins only:** Add beer, Stats, Manage (delete/photo). Regular logged-in
  users (testers) can only rate and browse. Admins come from secrets:
  `[admin] emails = ["..."]`. If that key is absent, every logged-in user is an
  admin (avoids lockout). Only test users can log in until the Google OAuth
  consent screen is published.

## How to make a change (deploy loop)

1. Edit locally. Test with `streamlit run app.py` (logged in, against the real
   Supabase, so you see real data).
2. `git add … && git commit -m "…" && git push`.
3. Streamlit Community Cloud auto-redeploys `main` within ~1–2 min. Secrets and
   Supabase data are untouched by a redeploy.

Secrets are **not** in the repo — set them in Streamlit Cloud → Settings →
Secrets (and in local `.streamlit/secrets.toml` for local runs). New secrets go
in both places, never in git.

## Gotchas we actually hit (save yourself the pain)

- **Schema changes are separate from code.** Adding/altering a column means an
  `ALTER TABLE` in Supabase's SQL editor AND a code change. A `git push` never
  touches the DB schema.
- **Postgres `numeric` can arrive as strings** over PostgREST. `core.py` already
  coerces score columns with `pd.to_numeric(...)`. Keep doing that for any new
  numeric column.
- **Supabase free projects pause after inactivity** → the client then returns a
  Cloudflare `522` / "JSON could not be generated" error. Fix: resume the project
  in the Supabase dashboard and wait until it's healthy. Not a code bug.
- **`redirect_uri` must match in three places:** the deployed app URL, the
  `redirect_uri` in Streamlit secrets, and Google's Authorized redirect URIs.
  A mismatch → `redirect_uri_mismatch` at login. Keep both localhost and the
  deployed `…/oauth2callback` registered in Google.
- **`st.user.is_logged_in` only works in the running app**, not on bare import —
  that's expected, not an error.
- **Don't run the migration twice** — it re-inserts and creates duplicates.
- **Renaming the Streamlit Cloud subdomain** (e.g. off `beerranker.streamlit.app`
  to match the "Meet and Drink" name) is a separate step from renaming the
  in-app text — it breaks the existing `redirect_uri` everywhere it's
  registered (Streamlit secrets, Google OAuth client), so update all three
  together (see the `redirect_uri` gotcha above) if it's ever done.

## Conventions

- Keep pure logic in `core.py`; keep `app.py` for Streamlit + Supabase calls.
- All DB writes must stay behind the login/admin checks in `app.py`.
- Don't hardcode secrets or the service key anywhere. Don't commit `secrets.toml`
  or `beers.db` (both gitignored).
