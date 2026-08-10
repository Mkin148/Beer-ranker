# 🍺 Beer Ranker — deployment guide (Supabase + Google login + Streamlit Cloud)

This turns the app into a shared, always-on website your group signs into with
Google. Data lives in Supabase (Postgres + photo storage); the app is hosted
free on Streamlit Community Cloud.

There are four stages: **Supabase**, **Google login**, **run locally**, then
**deploy**. Budget ~30–40 minutes the first time. You don't need to touch the
app code — only fill in secrets.

---

## Files in this folder

| File | What it is |
|------|-----------|
| `app.py` | The app (Google auth + Supabase). |
| `core.py` | Pure scoring/averaging logic. |
| `schema.sql` | Tables to create in Supabase. |
| `migrate_to_supabase.py` | One-time push of your existing beers into Supabase. |
| `requirements.txt` | Python dependencies. |
| `.streamlit/secrets.toml.example` | Template for your secrets. |
| `.gitignore` | Keeps secrets out of git. |

---

## Stage 1 — Supabase (database + photo storage)

1. Create a free account at supabase.com and click **New project**. Pick a name
   and a strong database password (you won't need it for this app). Wait for it
   to finish provisioning.
2. In the left menu open **SQL Editor**, paste the entire contents of
   `schema.sql`, and click **Run**. This creates the `beers` and `ratings`
   tables.
3. Open **Storage** → **New bucket**. Name it exactly `beer-photos` and tick
   **Public bucket** (so photos display in the app). Create it.
4. Open **Project Settings → API** and copy two values into a scratch file:
   - **Project URL** (looks like `https://abcd1234.supabase.co`)
   - **`service_role` key** (under Project API keys — the secret one, *not*
     `anon`). This stays server-side only; never put it in the browser or git.

---

## Stage 2 — Google login

1. Go to console.cloud.google.com and create a project (or reuse one).
2. **APIs & Services → OAuth consent screen**: choose **External**, give the app
   a name and your email. Under **Test users**, add every Google address that
   should be allowed to log in (you and your mates). Save. (Staying in "testing"
   is fine for a private group; only listed test users can sign in.)
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**.
   - Under **Authorized redirect URIs**, add:
     - `http://localhost:8501/oauth2callback`  (for local runs)
     - You'll add the deployed URL in Stage 4.
   - Create, then copy the **Client ID** and **Client secret**.

---

## Stage 3 — Run it locally first

1. Install Python 3.9+ then, in this folder:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy the secrets template and fill it in:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   Edit `.streamlit/secrets.toml`:
   - `cookie_secret` — generate one:
     `python -c "import secrets; print(secrets.token_hex(32))"`
   - `client_id`, `client_secret` — from Stage 2.
   - `[supabase] url`, `service_key` — from Stage 1.
3. Bring your existing beers across (optional but nice). With your old
   `beers.db` in this folder:
   ```bash
   export SUPABASE_URL="https://xxxx.supabase.co"
   export SUPABASE_SERVICE_KEY="your-service-role-key"
   python migrate_to_supabase.py --dry-run   # preview
   python migrate_to_supabase.py             # for real
   ```
   Your 15 beers arrive credited to taster `original@import.local`.
4. Run it:
   ```bash
   streamlit run app.py
   ```
   Open http://localhost:8501, click **Log in with Google**, and you're in.

---

## Stage 4 — Deploy to Streamlit Community Cloud

1. Push this folder to a **GitHub repo**. Confirm `.streamlit/secrets.toml` is
   **not** in the repo (the `.gitignore` handles this) — only the `.example`
   should be there.
2. At share.streamlit.io, **Create app**, point it at your repo and `app.py`,
   and deploy. You'll get a URL like `https://your-app.streamlit.app`.
3. In the app's **Settings → Secrets**, paste the full contents of your local
   `secrets.toml`, but change `redirect_uri` to your deployed URL:
   ```
   redirect_uri = "https://your-app.streamlit.app/oauth2callback"
   ```
4. Back in Google Cloud (Stage 2), add that same deployed callback to the
   OAuth client's **Authorized redirect URIs**:
   `https://your-app.streamlit.app/oauth2callback`
5. Reboot the app from Streamlit Cloud. Done — share the URL. Anyone on your
   Google **test users** list can log in and start rating.

---

## Notes & tradeoffs

- **Who can log in:** only the Google addresses you added as test users. To open
  it wider, publish the OAuth consent screen (Google may ask for verification
  for large audiences — not needed for a small group).
- **Security model:** the app authenticates people with Google and talks to
  Supabase using the `service_role` key from server-side secrets. Row-level
  security is enabled with no policies, so the public `anon` key can't touch the
  data — only your deployed app can. Keep the service key out of git and the
  browser.
- **Costs:** Supabase and Streamlit Community Cloud both have free tiers that
  comfortably cover a beer club. Photos are downscaled to ~900px before upload
  to stay light.
- **Renaming dimensions:** the five dimension names are constants at the top of
  `core.py` (`LABELS`). Edit there if you ever want to relabel — it flows through
  the whole app.
