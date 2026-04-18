"""Flask UI for browsing arxiv papers."""
from __future__ import annotations
import os
import json
import base64
import time
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g

from utils.config import today_str
from utils.supabase_client import get_admin_client, get_anon_client

from datetime import timedelta

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
app.permanent_session_lifetime = timedelta(days=30)
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _jwt_exp(token: str) -> float:
    """Return the expiry timestamp from a JWT without verifying the signature."""
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get('exp', 0))
    except Exception:
        return 0.0


def get_current_user():
    """Return the Supabase user for the current session, or None."""
    if "user" in g:
        return g.user

    token = session.get("access_token")
    if not token:
        g.user = None
        return None

    from types import SimpleNamespace
    cached_user_id = session.get("user_id")

    # Token still valid — use cached user info, no network call.
    if time.time() < _jwt_exp(token) - 60:
        if cached_user_id:
            g.user = SimpleNamespace(id=cached_user_id, email=session.get("user_email"))
            return g.user

    # Token expired — go straight to refresh (calling get_user with an expired
    # token always fails and just wastes a network round-trip).
    refresh = session.get("refresh_token")
    if refresh:
        try:
            client = get_anon_client()
            response = client.auth.refresh_session(refresh)
            session["access_token"] = response.session.access_token
            session["refresh_token"] = response.session.refresh_token
            user = response.session.user
            session["user_id"] = user.id
            session["user_email"] = getattr(user, "email", None)
            g.user = user
            return g.user
        except Exception:
            pass

    # Refresh failed (transient network error) — keep user logged in using
    # cached identity rather than forcing a re-login.
    if cached_user_id:
        g.user = SimpleNamespace(id=cached_user_id, email=session.get("user_email"))
        return g.user

    g.user = None
    return None


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET"])
def login():
    if get_current_user():
        return redirect(url_for("index"))
    error = request.args.get("error")
    return render_template("login.html", error=error)


@app.route("/login", methods=["POST"])
def login_post():
    email = request.form.get("email", "").strip()
    if not email:
        return render_template("login.html", error="Please enter your email.")
    try:
        client = get_anon_client()
        redirect_url = url_for("auth_callback", _external=True)
        client.auth.sign_in_with_otp({
            "email": email,
            "options": {"email_redirect_to": redirect_url},
        })
        return render_template("login.html", sent=True, email=email)
    except Exception as e:
        return render_template("login.html", error=f"Could not send email: {e}")


@app.route("/auth/callback")
def auth_callback():
    """Landing page after clicking the magic link.
    Supabase redirects here with tokens in the URL fragment (#).
    A small JS snippet reads the fragment and POSTs it to /auth/set-session."""
    return render_template("login.html", callback=True)


@app.route("/auth/set-session", methods=["POST"])
def set_session():
    """Receive access/refresh tokens from the client-side fragment and store in session."""
    data = request.json or {}
    access_token = data.get("access_token", "").strip()
    refresh_token = data.get("refresh_token", "").strip()
    if not access_token:
        return jsonify({"ok": False, "error": "no token"}), 400
    try:
        client = get_anon_client()
        response = client.auth.get_user(access_token)
        if response.user:
            session.permanent = True
            session["access_token"] = access_token
            session["refresh_token"] = refresh_token
            session["user_id"] = response.user.id
            session["user_email"] = getattr(response.user, "email", None)
            return jsonify({"ok": True})
    except Exception:
        pass
    return jsonify({"ok": False, "error": "invalid token"}), 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── DB helpers ────────────────────────────────────────────────────────────────

_papers_cache: dict = {}  # date -> list[dict], one entry kept at a time

def get_raw_papers(date: str) -> list[dict]:
    if date in _papers_cache:
        return _papers_cache[date]
    db = get_admin_client()
    result = db.table("papers").select("papers").eq("date", date).execute()
    papers = result.data[0]["papers"] if result.data else []
    _papers_cache.clear()
    _papers_cache[date] = papers
    return papers


def get_week_papers() -> list[dict]:
    from datetime import date, timedelta
    db = get_admin_client()
    today = date.today()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(7)]
    result = db.table("papers").select("papers").in_("date", dates).execute()
    seen: set[str] = set()
    merged: list[dict] = []
    for row in result.data:
        for p in row["papers"]:
            pid = p.get("id", "")
            if pid not in seen:
                seen.add(pid)
                merged.append(p)
    return merged


def get_keywords(user_id: str) -> list[str]:
    db = get_admin_client()
    result = db.table("keywords").select("keyword").eq("user_id", user_id).execute()
    return [r["keyword"] for r in result.data]


def get_followed_authors(user_id: str) -> list[str]:
    db = get_admin_client()
    result = db.table("followed_authors").select("author_name").eq("user_id", user_id).execute()
    return [r["author_name"] for r in result.data]


def get_reading_list(user_id: str) -> list[dict]:
    db = get_admin_client()
    result = db.table("reading_list").select("paper_json").eq("user_id", user_id).execute()
    return [r["paper_json"] for r in result.data]


def get_email_prefs(user_id: str) -> dict:
    db = get_admin_client()
    result = db.table("email_prefs").select("*").eq("user_id", user_id).execute()
    if result.data:
        row = result.data[0]
        # Migrate old single-digest schema to new split schema
        if "kw_enabled" not in row:
            enabled = row.get("enabled", True)
            row["kw_enabled"] = enabled and row.get("include_keywords", True)
            row["kw_days"] = [row.get("day_of_week", 4)]
            row["kw_limit"] = row.get("keyword_limit", 20)
            row["auth_enabled"] = enabled and row.get("include_authors", False)
            row["auth_days"] = [row.get("day_of_week", 4)]
        return row
    return {
        "startup_categories": "",
        "kw_enabled": True,  "kw_days": [4], "kw_limit": 20,
        "auth_enabled": False, "auth_days": [4],
    }


# ── App routes ────────────────────────────────────────────────────────────────

@app.route("/")
@require_auth
def index():
    date = request.args.get("date", today_str())
    return render_template("all_papers.html", date=date)


@app.route("/reading-list")
@require_auth
def reading_list_page():
    return render_template("reading_list.html")


@app.route("/settings")
@require_auth
def settings_page():
    return render_template("settings.html")


@app.route("/api/email-prefs")
@require_auth
def api_get_email_prefs():
    user = get_current_user()
    return jsonify(get_email_prefs(user.id))


@app.route("/api/email-prefs", methods=["POST"])
@require_auth
def api_save_email_prefs():
    user = get_current_user()
    data = request.json or {}
    prefs = {
        "user_id": user.id,
        "startup_categories": data.get("startup_categories", ""),
        "kw_enabled": bool(data.get("kw_enabled", True)),
        "kw_days": data.get("kw_days", [4]),
        "kw_limit": max(1, int(data.get("kw_limit", 20))),
        "auth_enabled": bool(data.get("auth_enabled", False)),
        "auth_days": data.get("auth_days", [4]),
    }
    db = get_admin_client()
    db.table("email_prefs").upsert(prefs).execute()
    return jsonify({"ok": True})


@app.route("/api/papers")
@require_auth
def api_papers():
    date = request.args.get("date", today_str())
    return jsonify({"date": date, "papers": get_raw_papers(date)})


@app.route("/api/papers/week")
@require_auth
def api_papers_week():
    return jsonify({"papers": get_week_papers()})


@app.route("/api/authors")
@require_auth
def api_authors():
    user = get_current_user()
    return jsonify({"authors": get_followed_authors(user.id)})


@app.route("/api/authors/follow", methods=["POST"])
@require_auth
def api_authors_follow():
    user = get_current_user()
    name = request.json.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    db = get_admin_client()
    db.table("followed_authors").upsert({"user_id": user.id, "author_name": name}).execute()
    return jsonify({"ok": True, "authors": get_followed_authors(user.id)})


@app.route("/api/authors/unfollow", methods=["POST"])
@require_auth
def api_authors_unfollow():
    user = get_current_user()
    name = request.json.get("name", "").strip()
    db = get_admin_client()
    db.table("followed_authors").delete().eq("user_id", user.id).eq("author_name", name).execute()
    return jsonify({"ok": True, "authors": get_followed_authors(user.id)})


@app.route("/api/keywords")
@require_auth
def api_keywords():
    user = get_current_user()
    return jsonify({"keywords": get_keywords(user.id)})


@app.route("/api/keywords/add", methods=["POST"])
@require_auth
def api_keywords_add():
    user = get_current_user()
    name = request.json.get("name", "").strip().lower()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    db = get_admin_client()
    db.table("keywords").upsert({"user_id": user.id, "keyword": name}).execute()
    return jsonify({"ok": True, "keywords": get_keywords(user.id)})


@app.route("/api/keywords/remove", methods=["POST"])
@require_auth
def api_keywords_remove():
    user = get_current_user()
    name = request.json.get("name", "").strip().lower()
    db = get_admin_client()
    db.table("keywords").delete().eq("user_id", user.id).eq("keyword", name).execute()
    return jsonify({"ok": True, "keywords": get_keywords(user.id)})


@app.route("/api/reading_list")
@require_auth
def api_reading_list():
    user = get_current_user()
    return jsonify({"papers": get_reading_list(user.id)})


@app.route("/api/reading_list/add", methods=["POST"])
@require_auth
def api_reading_list_add():
    user = get_current_user()
    paper = request.json.get("paper")
    if not paper or not paper.get("id"):
        return jsonify({"ok": False, "error": "paper required"}), 400
    db = get_admin_client()
    db.table("reading_list").upsert({
        "user_id": user.id,
        "paper_id": paper["id"],
        "paper_json": paper,
    }).execute()
    papers = get_reading_list(user.id)
    return jsonify({"ok": True, "ids": [p["id"] for p in papers]})


@app.route("/api/reading_list/remove", methods=["POST"])
@require_auth
def api_reading_list_remove():
    user = get_current_user()
    paper_id = request.json.get("id", "").strip()
    db = get_admin_client()
    db.table("reading_list").delete().eq("user_id", user.id).eq("paper_id", paper_id).execute()
    papers = get_reading_list(user.id)
    return jsonify({"ok": True, "ids": [p["id"] for p in papers]})


def _fetch_and_refresh():
    from fetcher.fetch import main as fetch_main
    fetch_main()
    _papers_cache.clear()


def _cleanup_old_papers():
    from datetime import date, timedelta
    db = get_admin_client()
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    db.table("papers").delete().lt("date", cutoff).execute()


def _start_scheduler():
    from zoneinfo import ZoneInfo
    from utils.email import send_weekly_digest
    chicago = ZoneInfo("America/Chicago")
    scheduler = BackgroundScheduler(timezone=chicago)
    scheduler.add_job(_fetch_and_refresh, "cron", day_of_week="mon,tue,wed,thu,fri", hour=0, minute=1)
    scheduler.add_job(_cleanup_old_papers, "cron", hour=10, minute=0)
    scheduler.add_job(send_weekly_digest, "cron", hour=8, minute=1)
    scheduler.start()


if os.environ.get("FLASK_ENV") != "development":
    _start_scheduler()


def main():
    print("Starting arxiv browser at http://localhost:5000")
    print("Press Ctrl+C to stop")
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
