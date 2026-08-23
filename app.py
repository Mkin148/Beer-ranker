"""
🍺 Beer Ranker — deployed edition (Google login + Supabase).

Public read / private write:
  - Anyone can view the Leaderboard, Browse, and Stats (no login).
  - Adding and rating beers requires Google login (st.login, OIDC).
  - The Manage tab (delete/photo) is limited to admins listed in secrets.

Storage: Supabase Postgres (beers + ratings) and Supabase Storage (photos).
Ranking: a beer's score is the average across every taster.

Config lives in .streamlit/secrets.toml — see DEPLOY.md. Never commit real secrets.
"""

import html
from uuid import uuid4

import altair as alt
import pandas as pd
import streamlit as st
from supabase import create_client

from core import (DIM_KEYS, LABELS, SCALE_MAX, build_leaderboard,
                  process_image, star_html)

st.set_page_config(page_title="Beer Ranker", page_icon="🍺", layout="wide")


# ---------------------------------------------------------------------------
# Supabase client (server-side; service key stays in secrets, never reaches
# the browser). Cached so it's created once per session.
# ---------------------------------------------------------------------------
@st.cache_resource
def sb():
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["service_key"])


def bucket_name():
    return st.secrets["supabase"].get("bucket", "beer-photos")


# ---- data access -----------------------------------------------------------
def fetch_beers():
    return sb().table("beers").select("*").order("id", desc=True).execute().data


def fetch_ratings():
    return sb().table("ratings").select("*").execute().data


def add_beer(name, style, origin, abv, description, photo_url):
    sb().table("beers").insert({
        "name": name, "style": style, "origin": origin, "abv": abv,
        "description": description, "photo_url": photo_url,
    }).execute()


def upsert_rating(beer_id, email, taster_name, scores, notes):
    sb().table("ratings").upsert({
        "beer_id": beer_id, "taster_email": email, "taster_name": taster_name,
        "notes": notes, **scores,
    }, on_conflict="beer_id,taster_email").execute()


def get_rating(beer_id, email):
    r = sb().table("ratings").select("*").eq("beer_id", beer_id) \
        .eq("taster_email", email).execute().data
    return r[0] if r else None


def delete_beer(beer_id):
    sb().table("beers").delete().eq("id", beer_id).execute()  # cascades ratings


def update_photo_url(beer_id, url):
    sb().table("beers").update({"photo_url": url}).eq("id", beer_id).execute()


def upload_photo(file):
    data = process_image(file)
    path = f"{uuid4().hex}.jpg"
    sb().storage.from_(bucket_name()).upload(
        path, data, {"content-type": "image/jpeg", "upsert": "true"})
    return sb().storage.from_(bucket_name()).get_public_url(path)


# ---------------------------------------------------------------------------
# Who is this? (guests allowed; login unlocks actions)
# ---------------------------------------------------------------------------
def admin_emails():
    """Admins come from secrets: [admin] emails = ["a@x.com", ...].
    If that key is absent, every logged-in user is treated as an admin (keeps
    the old behaviour and avoids locking yourself out). Add the list to lock
    Manage down once the app is public."""
    try:
        return {e.lower() for e in st.secrets["admin"]["emails"]}
    except Exception:
        return set()


logged_in = bool(st.user.is_logged_in)
EMAIL = st.user.email if logged_in else None
NAME = (st.user.name or st.user.email) if logged_in else None

_admins = admin_emails()
is_admin = logged_in and (not _admins or EMAIL.lower() in _admins)

with st.sidebar:
    st.header("🍺 Beer Ranker")
    if logged_in:
        st.caption(f"Signed in as **{NAME}**")
        if st.button("Log out"):
            st.logout()
    else:
        st.caption("Viewing as a guest")
        if st.button("Log in with Google", type="primary"):
            st.login()
    st.divider()
    st.caption("Meet up, crack a few open, and rank them together. The real "
               "goal is good company and soaking in the beer goodness — the "
               "ranking's just the excuse. Five dimensions, each out of 5.")


def score_inputs(prefix, existing=None):
    cols = st.columns(len(DIM_KEYS))
    out = {}
    for col, k in zip(cols, DIM_KEYS):
        default = float(existing[k]) if existing and existing.get(k) is not None else 2.5
        out[k] = col.slider(LABELS[k], 0.0, SCALE_MAX, default, 0.25, key=f"{prefix}_{k}")
    return out


def photo_or_placeholder(url, height=150):
    if pd.notna(url):
        st.image(url, use_container_width=True)
    else:
        st.markdown(f"<div style='height:{height}px;display:flex;"
                    "align-items:center;justify-content:center;"
                    "border:1px dashed #bbb;border-radius:8px;color:#999;'>"
                    "No photo</div>", unsafe_allow_html=True)


def beer_meta(row):
    meta = [p for p in (row.get("style"), row.get("origin")) if pd.notna(p) and p]
    if pd.notna(row.get("abv")):
        meta.append(f"{row['abv']:.1f}% ABV")
    return meta


esc = html.escape  # user-entered text goes through unsafe_allow_html below


def clickable_photo_css(key_prefix):
    """CSS to make a photo inside a st.container(key=f"{key_prefix}_...") the
    click target for the (invisible) button rendered right after it — st.image
    has no click handler, so this overlays the button on top of the photo.
    The button stays in the DOM (opacity, not display:none) so it's still
    reachable by keyboard and screen readers.

    Streamlit puts `position: relative` on the button's own element-container
    div (one level inside our keyed container), so that div — not ours — ends
    up as the absolute-positioned button's containing block, and it collapses
    to the button's own tiny content size (`width: fit-content` is set on it
    by Streamlit too). Fix: pin *that* wrapper (`> div:last-child`) to fill
    our keyed container, forcing its width instead of just the button inside
    it — confirmed by inspecting the live DOM, since neither issue is visible
    from the CSS alone."""
    st.markdown(f"""
        <style>
        div[class*="st-key-{key_prefix}_"] {{ position: relative; cursor: pointer; }}
        div[class*="st-key-{key_prefix}_"] > div:last-child {{
            position: absolute !important; inset: 0 !important; z-index: 1 !important;
            width: 100% !important; height: 100% !important;
        }}
        div[class*="st-key-{key_prefix}_"] > div:last-child .stButton,
        div[class*="st-key-{key_prefix}_"] > div:last-child .stButton button {{
            width: 100% !important; height: 100% !important; margin: 0 !important;
        }}
        div[class*="st-key-{key_prefix}_"] > div:last-child .stButton button {{
            opacity: 0; border: 0; padding: 0;
        }}
        </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Load data once per run (reads are open to everyone)
# ---------------------------------------------------------------------------
beers = fetch_beers()
ratings = fetch_ratings()
lb = build_leaderboard(beers, ratings)

st.title("🍺 Beer Ranker")

if "flash" in st.session_state:
    nm, av = st.session_state.pop("flash")
    st.balloons()
    if av is None:
        st.success(f"🍺 **{nm}** added — head to Rate beers to score it.")
    else:
        st.success(f"🍺 Saved — **{nm}** now averages {av:.2f}/5")

if not logged_in:
    st.info("👀 You're browsing as a guest — here's the ranking.")
    if st.button("🍺 Log in to join the beer magic", type="primary"):
        st.login()

# Build tabs based on who's here. Guests get Browse only — it already shows
# the ranking, so that's enough for someone who just wants to see the site.
tab_defs = []
if logged_in:
    tab_defs += [("add", "➕ Add beer"), ("rate", "⭐ Rate beers")]
tab_defs += [("browse", "🖼️ Browse")]
if logged_in:
    tab_defs += [("stats", "📊 Stats")]
if is_admin:
    tab_defs += [("manage", "🗂️ Manage")]

_objs = st.tabs([label for _, label in tab_defs])
T = {key: obj for (key, _), obj in zip(tab_defs, _objs)}


# ---------------------------------------------------------------------------
# Add beer  (login required)
# ---------------------------------------------------------------------------
if "add" in T:
    with T["add"]:
        st.subheader("Add a beer")
        st.caption("Add the details and a photo — score it from the Rate beers tab.")
        name = st.text_input("Beer name *", key="add_name", placeholder="e.g. Petrus Blonde",
                             autocomplete="off")
        c1, c2, c3 = st.columns(3)
        style = c1.text_input("Style", key="add_style", placeholder="e.g. Blonde ale",
                              autocomplete="off")
        origin = c2.text_input("Origin", key="add_origin", placeholder="e.g. Belgium",
                               autocomplete="off")
        abv = c3.number_input("Alcohol % (ABV)", key="add_abv", min_value=0.0,
                              max_value=100.0, step=0.1, value=None,
                              placeholder="e.g. 6.5")
        description = st.text_area("Description (shared)", key="add_desc",
                                   placeholder="What is this beer? Colour, vibe…")
        photo_file = st.file_uploader("Photo", type=["png", "jpg", "jpeg", "webp"],
                                      key="add_photo")

        if st.button("Add beer 🍺", type="primary", use_container_width=True):
            dupe = next((b for b in beers
                        if b["name"].strip().lower() == name.strip().lower()), None)
            if not name.strip():
                st.error("Give the beer a name first.")
            elif dupe:
                st.warning(f"**{dupe['name']}** is already in the list. Give this "
                          "one a different name, or head to **Rate beers** to "
                          "score the existing one instead.")
            else:
                with st.spinner("Saving…"):
                    url = upload_photo(photo_file) if photo_file else None
                    add_beer(name.strip(), style.strip(), origin.strip(), abv,
                             description.strip(), url)
                st.session_state["flash"] = (name.strip(), None)
                for key in ["add_name", "add_style", "add_origin", "add_abv",
                            "add_desc", "add_photo"]:
                    st.session_state.pop(key, None)
                st.rerun()


# ---------------------------------------------------------------------------
# Rate beers  (login required)
# ---------------------------------------------------------------------------
if "rate" in T:
    with T["rate"]:
        st.subheader("Rate a beer")
        if not beers:
            st.info("No beers yet — add one first.")
        else:
            bdf = pd.DataFrame(beers)
            picked_id = st.session_state.get("rate_beer_id")
            picked = bdf[bdf["id"] == picked_id] if picked_id is not None else bdf.iloc[0:0]

            if picked.empty:
                st.caption("Tap a beer's photo to start rating it.")
                clickable_photo_css("ratecard")
                search = st.text_input("🔎 Search", key="rate_search",
                                       placeholder="name or style…", autocomplete="off")
                view = bdf.sort_values("name")
                if search.strip():
                    q = search.lower()
                    view = view[view["name"].str.lower().str.contains(q, na=False) |
                                view["style"].fillna("").str.lower().str.contains(q, na=False)]
                for _, b in view.iterrows():
                    with st.container(border=True):
                        pcol, dcol = st.columns([1, 2])
                        with pcol:
                            with st.container(key=f"ratecard_{int(b['id'])}"):
                                photo_or_placeholder(b.get("photo_url"))
                                if st.button(f"Rate {b['name']}", key=f"pick_{b['id']}"):
                                    st.session_state["rate_beer_id"] = int(b["id"])
                                    st.rerun()
                            st.caption("Tap photo to rate")
                        with dcol:
                            st.markdown(f"### {b['name']}")
                            meta = beer_meta(b)
                            if meta:
                                st.caption(" · ".join(meta))
            else:
                brow = picked.iloc[0]
                bid = int(brow["id"])
                if st.button("← Choose a different beer", key="back_top"):
                    st.session_state.pop("rate_beer_id", None)
                    st.rerun()

                _, pmid, _ = st.columns([1, 2, 1])
                with pmid:
                    photo_or_placeholder(brow.get("photo_url"), height=220)
                st.markdown(f"<div style='text-align:center;'><h3 style='margin-bottom:4px;'>"
                            f"{esc(brow['name'])}</h3></div>", unsafe_allow_html=True)

                existing = get_rating(bid, EMAIL)
                if existing:
                    st.caption("You've rated this before — sliders show your last scores.")
                grow = lb[lb["beer_id"] == bid].iloc[0]
                if grow["n_raters"] > 0:
                    st.markdown(f"Group so far: {star_html(grow['avg'], 16)} "
                                f"**{grow['avg']:.2f}/5** from {int(grow['n_raters'])} taster(s)",
                                unsafe_allow_html=True)

                scores = score_inputs("rate", existing)
                notes = st.text_input("Your note (optional)",
                                      value=(existing or {}).get("notes") or "",
                                      key="rate_notes", autocomplete="off")
                avg = sum(scores.values()) / len(DIM_KEYS)
                st.markdown(star_html(avg, 24) + f" &nbsp;<b>{avg:.2f}/5</b>",
                            unsafe_allow_html=True)

                if st.button("Save my scores ⭐", type="primary", use_container_width=True):
                    with st.spinner("Saving…"):
                        upsert_rating(bid, EMAIL, NAME, scores, notes.strip())
                        new_lb = build_leaderboard(fetch_beers(), fetch_ratings())
                        new_avg = float(new_lb[new_lb["beer_id"] == bid]["avg"].iloc[0])
                    st.session_state["flash"] = (brow["name"], new_avg)
                    for k in DIM_KEYS:
                        st.session_state.pop(f"rate_{k}", None)
                    st.session_state.pop("rate_notes", None)
                    st.rerun()

                if st.button("← Choose a different beer", key="back_bottom"):
                    st.session_state.pop("rate_beer_id", None)
                    st.rerun()


# ---------------------------------------------------------------------------
# Browse & Leaderboard  (public) — one view: beers ranked by score with
# photos; click a beer's photo to open its full score breakdown.
# ---------------------------------------------------------------------------
with T["browse"]:
    if lb.empty:
        st.info("Nothing to browse yet.")
    else:
        rdf = pd.DataFrame(ratings)
        if not rdf.empty:
            for k in DIM_KEYS:
                rdf[k] = pd.to_numeric(rdf[k], errors="coerce")

        selected = st.session_state.get("selected_beer")
        match = lb[lb["beer_id"] == selected] if selected is not None else lb.iloc[0:0]

        if not match.empty:
            row = match.iloc[0]
            if st.button("← Back to all beers"):
                st.session_state.pop("selected_beer", None)
                st.rerun()

            _, pmid, _ = st.columns([1, 2, 1])
            with pmid:
                photo_or_placeholder(row.get("photo_url"), height=260)

            meta = beer_meta(row)
            meta_html = (f"<div style='color:#888;'>{esc(' · '.join(str(m) for m in meta))}"
                        f"</div>" if meta else "")
            if row["n_raters"] > 0:
                score_html = (star_html(row["avg"], 26) +
                             f" <b>{row['avg']:.2f}/5</b> "
                             f"<span style='color:#888;'>· {int(row['n_raters'])} "
                             f"taster(s)</span>")
            else:
                score_html = "<span style='color:#888;'>No ratings yet</span>"
            st.markdown(
                f"<div style='text-align:center;'>"
                f"<h2 style='margin-bottom:2px;'>{esc(row['name'])}</h2>"
                f"{meta_html}"
                f"<div style='margin-top:8px;'>{score_html}</div>"
                f"</div>", unsafe_allow_html=True)

            desc = row.get("description")
            if pd.notna(desc) and desc:
                st.markdown(f"<p style='text-align:center;color:#444;max-width:420px;"
                            f"margin:14px auto;'>{esc(desc)}</p>", unsafe_allow_html=True)

            if row["n_raters"] > 0:
                st.write("")
                st.markdown("<div style='text-align:center;font-weight:600;'>"
                            "Score breakdown</div>", unsafe_allow_html=True)
                bars = ""
                for k in DIM_KEYS:
                    val = row[k]
                    pct = max(0.0, min(100.0, val / SCALE_MAX * 100))
                    bars += (
                        f"<div style='max-width:320px;margin:8px auto;'>"
                        f"<div style='display:flex;justify-content:space-between;"
                        f"font-size:0.9em;'><span>{LABELS[k]}</span>"
                        f"<span><b>{val:.2f}</b></span></div>"
                        f"<div style='background:#eee;border-radius:6px;height:8px;"
                        f"overflow:hidden;'><div style='background:#f5a623;width:{pct}%;"
                        f"height:100%;'></div></div></div>")
                st.markdown(bars, unsafe_allow_html=True)
                st.markdown(f"<div style='text-align:center;color:#888;'>"
                            f"Total {row['total']:.2f} / 25</div>", unsafe_allow_html=True)

            if not rdf.empty:
                mine = rdf[rdf["beer_id"] == row["beer_id"]]
                if not mine.empty:
                    st.write("")
                    st.markdown(f"<div style='text-align:center;font-weight:600;'>"
                                f"Individual scores ({mine['taster_email'].nunique()})"
                                f"</div>", unsafe_allow_html=True)
                    cards = ""
                    for _, tr in mine.sort_values("taster_name").iterrows():
                        t_avg = sum(tr[k] for k in DIM_KEYS) / len(DIM_KEYS)
                        note = tr.get("notes")
                        note_html = (f"<div style='color:#888;font-size:0.85em;"
                                     f"font-style:italic;'>“{esc(note)}”</div>"
                                     if pd.notna(note) and note else "")
                        cards += (
                            f"<div style='max-width:320px;margin:10px auto 0;"
                            f"text-align:center;border-top:1px solid #eee;"
                            f"padding-top:8px;'><b>{esc(tr['taster_name'])}</b><br>"
                            f"{star_html(t_avg, 16)} {t_avg:.2f}/5{note_html}</div>")
                    st.markdown(cards, unsafe_allow_html=True)

        else:
            rated = lb[lb["n_raters"] > 0].sort_values("avg", ascending=False) \
                .reset_index(drop=True)
            if not rated.empty:
                medals = ["🥇", "🥈", "🥉"]
                border = ["#f5a623", "#b8b8b8", "#cd7f32"]
                pcols = st.columns(min(3, len(rated)))
                for i, col in enumerate(pcols):
                    r = rated.iloc[i]
                    col.markdown(
                        f"<div style='text-align:center;border:2px solid {border[i]};"
                        f"border-radius:12px;padding:12px 6px;'>"
                        f"<div style='font-size:2em;'>{medals[i]}</div>"
                        f"<div style='font-weight:700;'>{esc(r['name'])}</div>"
                        f"<div>{star_html(r['avg'], 16)}</div>"
                        f"<div style='color:#888;'>{r['avg']:.2f}/5 · {int(r['n_raters'])} 🧑"
                        f"</div></div>", unsafe_allow_html=True)
                st.write("")

            clickable_photo_css("photocard")

            search = st.text_input("🔎 Search", key="browse_search", placeholder="name or style…")
            view = lb.sort_values("avg", ascending=False, na_position="last")
            if search.strip():
                q = search.lower()
                view = view[view["name"].str.lower().str.contains(q, na=False) |
                            view["style"].fillna("").str.lower().str.contains(q, na=False)]
            for _, r in view.iterrows():
                with st.container(border=True):
                    pcol, dcol = st.columns([1, 2])
                    with pcol:
                        with st.container(key=f"photocard_{int(r['beer_id'])}"):
                            photo_or_placeholder(r.get("photo_url"))
                            if st.button(f"View {r['name']} details",
                                        key=f"view_{r['beer_id']}"):
                                st.session_state["selected_beer"] = int(r["beer_id"])
                                st.rerun()
                        st.caption("Tap photo for details")
                    with dcol:
                        st.markdown(f"### {r['name']}")
                        if r["n_raters"] > 0:
                            st.markdown(star_html(r["avg"], 20) +
                                        f" &nbsp;<b>{r['avg']:.2f}/5</b> "
                                        f"<span style='color:#888;'>· {int(r['n_raters'])} "
                                        f"taster(s)</span>", unsafe_allow_html=True)
                        else:
                            st.caption("No ratings yet")
                        meta = beer_meta(r)
                        if meta:
                            st.caption(" · ".join(meta))
                        desc = r.get("description")
                        if pd.notna(desc) and desc:
                            st.write(desc)


# ---------------------------------------------------------------------------
# Stats  (logged-in users)
# ---------------------------------------------------------------------------
def render_stats():
    rated = lb[lb["n_raters"] > 0] if not lb.empty else lb
    if rated.empty:
        st.info("Log some ratings and charts will show up here.")
    else:
        st.markdown("**Group average per dimension**")
        dim_avgs = pd.DataFrame({"Dimension": [LABELS[k] for k in DIM_KEYS],
                                 "Average": [rated[k].mean() for k in DIM_KEYS]})
        st.altair_chart(alt.Chart(dim_avgs).mark_bar().encode(
            x=alt.X("Average:Q", scale=alt.Scale(domain=[0, SCALE_MAX])),
            y=alt.Y("Dimension:N", sort=[LABELS[k] for k in DIM_KEYS]),
            tooltip=["Dimension", alt.Tooltip("Average:Q", format=".2f")]
        ).properties(height=200), use_container_width=True)

        rdf = pd.DataFrame(ratings)
        if not rdf.empty and rdf["taster_email"].nunique() > 1:
            st.markdown("**Average score given, by taster** (who's the harsh critic?)")
            for k in DIM_KEYS:
                rdf[k] = pd.to_numeric(rdf[k], errors="coerce")
            rdf["overall"] = rdf[DIM_KEYS].mean(axis=1)
            by_t = rdf.groupby("taster_name")["overall"].mean().reset_index()
            st.altair_chart(alt.Chart(by_t).mark_bar().encode(
                x=alt.X("overall:Q", title="Average score given",
                        scale=alt.Scale(domain=[0, SCALE_MAX])),
                y=alt.Y("taster_name:N", title="Taster", sort="-x"),
                tooltip=["taster_name", alt.Tooltip("overall:Q", format=".2f")]
            ).properties(height=max(120, 32 * len(by_t))), use_container_width=True)

        abv_df = rated.dropna(subset=["abv"])
        if not abv_df.empty:
            st.markdown("**ABV vs group score**")
            st.altair_chart(alt.Chart(abv_df).mark_circle(size=90, opacity=0.7).encode(
                x=alt.X("abv:Q", title="ABV %"),
                y=alt.Y("avg:Q", title="Group avg", scale=alt.Scale(domain=[0, SCALE_MAX])),
                tooltip=[alt.Tooltip("name:N", title="Beer"),
                         alt.Tooltip("abv:Q", format=".1f"),
                         alt.Tooltip("avg:Q", format=".2f")]
            ), use_container_width=True)


if "stats" in T:
    with T["stats"]:
        render_stats()


# ---------------------------------------------------------------------------
# Manage  (admins only)
# ---------------------------------------------------------------------------
if "manage" in T:
    with T["manage"]:
        if not beers:
            st.info("Nothing to manage yet.")
        else:
            bdf = pd.DataFrame(beers)
            st.subheader("Add or replace a photo")
            pick = bdf.apply(lambda r: f'#{int(r["id"])} — {r["name"]}', axis=1)
            chosen = st.selectbox("Beer", pick, key="photo_pick")
            pid = int(chosen.split(" ")[0].lstrip("#"))
            up = st.file_uploader("Upload photo", type=["png", "jpg", "jpeg", "webp"],
                                  key="mng_photo")
            if up and st.button("Save photo"):
                with st.spinner("Uploading…"):
                    update_photo_url(pid, upload_photo(up))
                st.success("Photo saved.")
                st.rerun()

            st.divider()
            st.subheader("Delete a beer")
            st.caption("Removes the beer and every taster's rating of it.")
            dchosen = st.selectbox("Beer to remove", pick, key="del_pick")
            did = int(dchosen.split(" ")[0].lstrip("#"))
            if st.button("Delete", type="primary"):
                delete_beer(did)
                st.success("Deleted.")
                st.rerun()

            st.divider()
            st.subheader("Export")
            if ratings:
                merged = pd.DataFrame(ratings).merge(
                    bdf[["id", "name", "style"]], left_on="beer_id", right_on="id",
                    suffixes=("", "_beer"))
                st.download_button("Download all ratings as CSV",
                                   data=merged.to_csv(index=False),
                                   file_name="beer_ratings.csv", mime="text/csv")