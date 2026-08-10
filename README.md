# 🍺 Beer Ranker (deployed edition)

A shared beer-ranking website. Your group signs in with **Google**, each person
scores beers across five dimensions (Packaging Presentation, Look, Smell, Taste,
Drinkability — each out of 5), and every beer is ranked by the **average across
all tasters**. Data and photos live in **Supabase**; hosting is **Streamlit
Community Cloud**.

## Set it up

Full step-by-step is in **DEPLOY.md** — four stages (Supabase, Google login,
run locally, deploy). You only fill in secrets; no code changes needed.

Quick version:
1. Create a Supabase project, run `schema.sql`, make a public `beer-photos` bucket.
2. Create a Google OAuth client (Web app) with redirect `…/oauth2callback`.
3. `pip install -r requirements.txt`, fill `.streamlit/secrets.toml`, then
   `streamlit run app.py`.
4. Push to GitHub, deploy on Streamlit Cloud, paste secrets, update the redirect
   URL in secrets + Google.

Bring your existing beers over once with `python migrate_to_supabase.py`.

## How it works

- **Log in with Google** → your account is your taster identity, so scores stay
  separate automatically.
- **Add beer** enters a beer once (name, style, photo, description) plus your
  scores; **Rate beers** lets anyone else score it. Re-scoring replaces your own
  previous scores.
- **Leaderboard** ranks by the group average with a podium and taster counts;
  **Browse** shows each beer's photo, description, and every person's scores;
  **Stats** includes a "who scores harshest" comparison.

## Files

`app.py` (UI + Supabase/auth), `core.py` (pure scoring logic, unit-testable),
`schema.sql`, `migrate_to_supabase.py`, `requirements.txt`,
`.streamlit/secrets.toml.example`, `.gitignore`, `DEPLOY.md`.
