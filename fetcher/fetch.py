"""Fetch today's new papers from arxiv listing pages."""
from __future__ import annotations
import re
import time
import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

from utils.config import load_config, today_str
from utils.supabase_client import get_admin_client

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_LIST = "https://arxiv.org/list/{category}/new"
BATCH_SIZE = 200
DELAY = 3  # seconds between API requests (arxiv rate limit)


_TYPE_PRIORITY = {"new": 0, "cross": 1, "replacement": 2}


def get_new_ids(category: str) -> dict[str, list[str]]:
    """Scrape today's paper IDs from arxiv /list/{cat}/new, split by section.

    Returns {"new": [...], "cross": [...], "replacement": [...]}.
    """
    url = ARXIV_LIST.format(category=category)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    html = resp.text

    sections: dict[str, list[str]] = {"new": [], "cross": [], "replacement": []}
    current: str | None = None

    for part in re.split(r'<h3[^>]*>', html, flags=re.IGNORECASE):
        head = part[:120].lower()
        if "new submission" in head:
            current = "new"
        elif "cross-list" in head or "cross list" in head:
            current = "cross"
        elif "replacement" in head:
            current = "replacement"

        if current:
            ids = list(dict.fromkeys(re.findall(r'href\s*="/abs/(\d{4}\.\d{4,5})', part)))
            sections[current].extend(ids)

    total = sum(len(v) for v in sections.values())
    print(f"    {category}: {total} papers "
          f"(new={len(sections['new'])}, cross={len(sections['cross'])}, "
          f"replacements={len(sections['replacement'])})")
    return sections


def fetch_details(ids: list[str]) -> list[dict]:
    """Fetch full paper metadata from the arXiv API for a list of IDs."""
    papers = {}
    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i:i + BATCH_SIZE]
        params = {
            "id_list": ",".join(batch),
            "max_results": len(batch),
        }
        print(f"  Fetching details for {len(batch)} papers ({i}–{i+len(batch)})...")
        resp = requests.get(ARXIV_API, params=params, timeout=60)
        resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            arxiv_id = entry.id.split("/abs/")[-1]
            # Strip version suffix for dedup key
            base_id = re.sub(r'v\d+$', '', arxiv_id)
            if base_id in papers:
                continue

            cats = [t.term for t in entry.get("tags", [])]
            authors = [a.get("name", "") for a in entry.get("authors", [])]

            papers[base_id] = {
                "id": arxiv_id,
                "title": entry.title.replace("\n", " ").strip(),
                "abstract": entry.summary.replace("\n", " ").strip(),
                "authors": authors,
                "categories": cats,
                "primary_category": cats[0] if cats else "",
                "published": entry.get("published", ""),
                "updated": entry.get("updated", ""),
                "url": entry.link,
                "pdf_url": next(
                    (l.href for l in entry.get("links", [])
                     if l.get("type") == "application/pdf"),
                    f"https://arxiv.org/pdf/{arxiv_id}"
                ),
            }

        if i + BATCH_SIZE < len(ids):
            time.sleep(DELAY)

    return list(papers.values())


def main():
    config = load_config()
    date = today_str()

    categories = config.get("categories", ["physics"])
    print(f"Fetching today's new arxiv papers for {date}...")
    print(f"Categories: {', '.join(categories)}\n")

    # Collect all IDs and record every (category, type) appearance per paper.
    all_ids: list[str] = []
    seen: set[str] = set()
    appearances_map: dict[str, list[dict]] = {}  # base_id -> [{category, type}, ...]

    for cat in categories:
        try:
            sections = get_new_ids(cat)
        except Exception as e:
            print(f"  Warning: could not fetch {cat}: {e}")
            time.sleep(1)
            continue

        for type_, ids in sections.items():
            for id_ in ids:
                base = re.sub(r'v\d+$', '', id_)
                if base not in seen:
                    seen.add(base)
                    all_ids.append(id_)
                    appearances_map[base] = []
                app = {"category": cat, "type": type_}
                if app not in appearances_map[base]:
                    appearances_map[base].append(app)
        time.sleep(1)  # be polite between listing page requests

    print(f"\n{len(all_ids)} unique papers across all categories")

    if not all_ids:
        print("No papers found. (Weekend / holiday with no new submissions?)")
        return

    print("Fetching full paper details...\n")
    papers = fetch_details(all_ids)

    for p in papers:
        base = re.sub(r'v\d+$', '', p["id"])
        apps = appearances_map.get(base, [])
        p["appearances"] = apps
        # submission_type = highest-priority type across all appearances (for flat view)
        if apps:
            p["submission_type"] = min(apps, key=lambda a: _TYPE_PRIORITY.get(a["type"], 99))["type"]
        else:
            p["submission_type"] = "new"

    db = get_admin_client()
    db.table("papers").upsert({"date": date, "papers": papers}).execute()
    print(f"\nSaved {len(papers)} papers → Supabase (date={date})")


if __name__ == "__main__":
    main()
