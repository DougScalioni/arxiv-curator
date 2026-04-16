# arxiv-curator

A personal arxiv browser that mirrors the daily new-paper listings across physics categories. Papers are fetched directly from arXiv's announcement pages, so what you see matches exactly what arXiv shows as "new" each day.

## Features

- **Full daily listings** — fetches every paper announced today across all configured categories, matching arXiv's own counts exactly
- **Category browser** — collapsible checkbox tree; click a category name to isolate it
- **Keyword tracking** — add keywords to follow; each shows how many papers matched today
- **Author following** — click any author name to follow them; their papers are highlighted
- **Search** — filter by one or more phrases using `phrase1 && phrase2`
- **LaTeX rendering** — math in titles and abstracts is rendered via KaTeX
- **Category tooltips** — hover over any category code to see its full name

## Setup

```bash
git clone <repo-url>
cd arxiv-curator
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

Edit `config.yaml` to set your categories and keywords.

## Usage

**Fetch today's papers:**
```bash
python -m fetcher
```

**Start the browser:**
```bash
python -m curation_ui
```

Then open [http://localhost:5000](http://localhost:5000).

## Configuration

```yaml
# config.yaml

categories:
  - astro-ph
  - gr-qc
  - hep-th
  - quant-ph
  # ... any arxiv category

keywords:
  - dark matter
  - gravitational waves
  - black hole
```

Keywords and followed authors can also be managed directly from the browser UI and are saved to `data/keywords.json` and `data/followed_authors.json`.

## Automation

A GitHub Actions workflow (`.github/workflows/daily.yml`) runs the fetcher automatically each day at 08:00 UTC and commits the results. To enable it, push the repo to GitHub — no secrets are required for fetching alone.

## Project Structure

```
fetcher/       — fetches daily listings from arxiv.org
curation_ui/   — Flask browser UI
scorer/        — optional: keyword + Claude AI relevance scoring
site_builder/  — optional: generates a static GitHub Pages site
emailer/       — optional: sends a daily digest via SendGrid
data/          — paper data and user settings (gitignored)
```
