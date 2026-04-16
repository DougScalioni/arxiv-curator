"""Weekly digest email via Gmail SMTP."""
from __future__ import annotations
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, timedelta


def _get_week_papers() -> list[dict]:
    from utils.supabase_client import get_admin_client
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


def _top_papers(papers: list[dict], keywords: list[str]) -> list[tuple[dict, list[str]]]:
    kw_lower = [kw.lower() for kw in keywords]
    scored = []
    for p in papers:
        text = ((p.get("title") or "") + " " + (p.get("abstract") or "")).lower()
        matched = [kw for kw in kw_lower if kw in text]
        if matched:
            scored.append((p, matched))
    scored.sort(key=lambda x: -len(x[1]))
    return scored[:50]


def _build_html(top: list[tuple[dict, list[str]]], keywords: list[str]) -> str:
    week_start = (date.today() - timedelta(days=6)).strftime("%b %d")
    week_end = date.today().strftime("%b %d, %Y")
    kw_list = ", ".join(keywords)

    rows = []
    for i, (p, matched) in enumerate(top, 1):
        authors = p.get("authors", [])
        author_str = ", ".join(authors[:5]) + (" et al." if len(authors) > 5 else "")
        url = p.get("url", "#")
        pdf = p.get("pdf_url", "")
        pdf_link = f'<a href="{pdf}" style="font-size:11px;color:#1777bc;margin-left:8px;">PDF</a>' if pdf else ""
        rows.append(f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #eee;vertical-align:top;">
            <div style="font-size:14px;font-weight:bold;margin-bottom:4px;">
              <span style="color:#bbb;margin-right:6px;">{i}.</span>
              <a href="{url}" style="color:#b31b1b;text-decoration:none;">{p.get("title","")}</a>
            </div>
            <div style="font-size:12px;color:#555;margin-bottom:3px;">{author_str}</div>
            <div style="font-size:11px;color:#888;margin-bottom:4px;">
              {p.get("primary_category","")} &middot; {(p.get("published") or "")[:10]}
            </div>
            <div style="font-size:11px;color:#d47500;">
              keywords: {", ".join(matched)}{pdf_link}
            </div>
          </td>
        </tr>""")

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Helvetica,Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px;">
<table style="max-width:640px;margin:0 auto;background:#fff;border:1px solid #ddd;border-collapse:collapse;">
  <tr><td style="background:#b31b1b;padding:16px 24px;">
    <div style="color:#fff;font-size:18px;font-weight:bold;">arXiv curator
      <span style="font-weight:normal;opacity:0.8;font-size:14px;"> // weekly digest</span>
    </div>
    <div style="color:rgba(255,255,255,0.7);font-size:12px;margin-top:4px;">{week_start} – {week_end}</div>
  </td></tr>
  <tr><td style="padding:16px 24px 8px;">
    <div style="font-size:12px;color:#888;">Your keywords: <span style="color:#555;">{kw_list}</span></div>
    <div style="font-size:13px;color:#333;margin-top:6px;">Top {len(top)} papers matching your keywords this week:</div>
  </td></tr>
  <tr><td style="padding:0 24px 24px;">
    <table style="width:100%;border-collapse:collapse;">{"".join(rows)}</table>
  </td></tr>
  <tr><td style="padding:12px 24px;border-top:1px solid #eee;font-size:11px;color:#bbb;text-align:center;">
    <a href="https://arxiv-curator.fly.dev" style="color:#bbb;">open app</a>
  </td></tr>
</table>
</body>
</html>"""


def send_weekly_digest() -> None:
    from utils.supabase_client import get_admin_client

    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_password:
        print("Weekly digest skipped: GMAIL_USER or GMAIL_APP_PASSWORD not configured")
        return

    db = get_admin_client()
    papers = _get_week_papers()
    if not papers:
        print("Weekly digest: no papers this week")
        return

    subject = f"arXiv digest — week of {(date.today() - timedelta(days=6)).strftime('%b %d')}"
    users = db.auth.admin.list_users()
    sent = 0

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_password)

        for user in users:
            email = getattr(user, "email", None)
            user_id = getattr(user, "id", None)
            if not email or not user_id:
                continue

            kw_data = db.table("keywords").select("keyword").eq("user_id", user_id).execute()
            keywords = [r["keyword"] for r in kw_data.data]
            if not keywords:
                continue

            top = _top_papers(papers, keywords)
            if not top:
                continue

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = gmail_user
            msg["To"] = email
            msg.attach(MIMEText(_build_html(top, keywords), "html"))

            try:
                server.sendmail(gmail_user, email, msg.as_string())
                sent += 1
                print(f"  Digest sent to {email} ({len(top)} papers)")
            except Exception as e:
                print(f"  Failed to send to {email}: {e}")

    print(f"Weekly digest done: {sent} emails sent")
