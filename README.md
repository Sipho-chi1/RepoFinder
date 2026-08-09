WTC-GVXNPWBA

# Repo Finder

A data engineering pipeline that helps beginner developers find open-source
repositories matched to what they are currently learning — and ranks the
open issues in those repositories from easy to hard.

> **Status:** early prototype · **Elective:** Data Engineering (WeThinkCode_)
> Backend pipeline runs end-to-end for Python. CLI only — no API or front
> end yet (see [Current status](#current-status)).

---

## The problem

Most beginner developers struggle to find repositories that match the
skills they are learning. Existing "good first issue" lists surface
beginner-friendly issues but do little to confirm a repo actually uses the
skills a learner is studying, or to convey how hard a given issue really is
to contribute to — the label is a convention maintainers apply
inconsistently, not a guarantee. This project closes that gap: a learner
states a language and experience level, and the pipeline returns repos that
(a) genuinely use that language and (b) have issues an LLM has actually read
and rated for difficulty.

[![Watch the demo](https://img.shields.io/badge/demo-YouTube-red?logo=youtube&logoColor=white)](https://youtu.be/rB8NZnVxZo8)

---

## Architecture

```
GitHub API
    │  (extract: search repos, cheap in-memory filter)
    ▼
data/raw/*.json         ← raw landing zone (untouched API responses)
    │  (transform: flatten JSON into a repo table)
    ▼
PostgreSQL               ← repositories, repo_languages, repo_issues
    │  (narrow: cheap filter, then paced GitHub calls for languages + issues)
    ▼
SQL narrow filter         ← language share ≥ threshold, skips already-analysed issues
    │
    ▼
LLM analysis (Gemini)     ← runs only on the narrowed shortlist; cached in repo_analysis
    │
    ▼
CLI                       ← prompts for language + experience level, prints ranked matches
```

**Design principle — cheap before expensive.** Filtering happens in stages,
cheapest first: the initial GitHub search query already restricts to recent,
starred, active repos; `narrow.py` does a free in-memory filter (not a fork,
has a description) before making a single paced API call; and the LLM —
the most expensive step — only ever runs on issues not already cached in
`repo_analysis`.

---

## Tech stack

| Layer            | Technology                |
| ----------------- | -------------------------- |
| Ingestion / glue | Python                     |
| Database         | PostgreSQL                |
| Schema & queries | SQL (via pandas / SQLAlchemy) |
| LLM analysis     | Gemini (`google-genai`)   |
| Interface        | Command-line (Python)     |

---

## Data model

Three ingested tables plus one cache table, normalised because the source
JSON has one-to-many relationships (one repo has many languages and many
issues):

- **repositories** — one row per repo (id, name, full_name, description,
  html_url, owner info)
- **repo_languages** — one row per repo-language pair (repo_id, language,
  bytes); many per repo
- **repo_issues** — one row per open issue (repo_id, issue_number, title,
  labels, state); many per repo
- **repo_analysis** — cached LLM output per issue (repo_id, issue_number,
  experience_level, reasoning, analyzed_at) — the cache that keeps the same
  issue from ever being sent to the LLM twice

`repositories`, `repo_languages`, and `repo_issues` are created implicitly
by pandas (`to_sql`) during load; only `repo_analysis` has an explicit
`CREATE TABLE` (see `backend/db/create_repo_analysis.sql`).

---

## Project structure

```
REPO_FINDER/
├── README.md
├── .gitignore
├── .env.example              # template — variable names, no secrets
│
├── backend/
│   ├── .env                  # GITHUB_TOKEN, GEMINI_API_KEY, DB_PASSWORD (gitignored)
│   ├── requirements.txt
│   │
│   ├── db/
│   │   ├── create_repo_analysis.sql   # CREATE TABLE for the cache table
│   │   ├── update_repo_analysis.sql   # INSERT used by save_analysis()
│   │   └── repo_analysis.py           # helper to create the cache table
│   │
│   ├── ingest/
│   │   ├── github_client.py  # EXTRACT: search GitHub, cheap filter, save raw JSON
│   │   ├── transform.py      # TRANSFORM: flatten JSON into a repo dataframe
│   │   ├── load.py           # LOAD: write the repo dataframe to Postgres
│   │   └── narrow.py         # NARROW: cheap filter, then fetch languages + issues per repo
│   │
│   ├── analysis/
│   │   ├── llm_client.py     # calls Gemini
│   │   └── analyze.py        # builds the prompt, runs the LLM, caches results
│   │
│   ├── api/
│   │   └── main.py           # CLI entry point (interactive prompt, not yet a web API)
│   │
│   ├── scripts/
│   │   └── live_smoke_test.py
│   │
│   ├── tests/                 # pytest suite covering ingest, analysis, db, CLI
│   │
│   └── run_pipeline.py        # orchestrator: extract → transform → load → narrow → analyse
│
└── data/
    └── raw/                    # raw API JSON (gitignored)
```

---

## Setup

1. **Clone and enter the project**
2. **Create `backend/.env`** from `.env.example` and fill in your keys
   (GitHub personal access token, Gemini API key, Postgres password)
3. **Install Python dependencies** — `pip install -r backend/requirements.txt`
4. **Create the database** — a local Postgres database named `repo_finder`,
   then run `backend/db/create_repo_analysis.sql` against it (the other
   three tables are created automatically the first time the pipeline runs)
5. **Run the pipeline** — `python backend/run_pipeline.py` (fetches fresh
   data from GitHub, populates Postgres, runs LLM analysis on Python issues)
6. **Run the CLI** — `python backend/api/main.py`

> `.env` and `data/` are gitignored. Never commit API keys.

---

## Pipeline stages

1. **Extract** — `github_client.py` searches GitHub for repos (recent,
   ≥10 stars, has good-first-issues), applies a threshold filter
   (stars, forks, open issues), and saves the raw JSON to `data/raw/`.
2. **Transform** — `transform.py` flattens the nested JSON into a flat
   dataframe of repo-level fields.
3. **Load** — `load.py` writes that dataframe into the `repositories` table.
4. **Narrow** — `narrow.py` does a free in-memory filter (drops forks and
   repos with no description), then makes paced, rate-limit-aware calls to
   fetch each survivor's language breakdown and open issues, loading both
   into Postgres.
5. **Analyse** — `analyze.py` pulls issues where the target language makes
   up a large enough share of the repo and that aren't already cached,
   prompts Gemini for a difficulty rating, skills, and time estimate per
   issue, and writes the result to `repo_analysis`.
6. **Serve** — `api/main.py` is currently a CLI: it lists available
   languages, asks for a language and experience level, and prints matching
   repos ranked by language share.

---

## Current status

What works end-to-end right now:
- Full pipeline run for Python: GitHub → Postgres → LLM analysis → CLI results
- Caching, so re-running the pipeline doesn't re-analyse the same issue twice
- A pytest suite covering ingestion, analysis, the database layer, and the CLI

What's not built yet (planned next):
- **Web API and front end** — the project currently ends at a terminal
  prompt; FastAPI and React are the intended next layer, not yet started
- **Multi-language support** — `run_pipeline.py` currently calls
  `run_analysis(engine, "Python")` directly; the schema and filtering logic
  are language-agnostic, but the orchestration isn't parameterised yet
- **Scaling ingestion** — works against a small candidate set; hasn't been
  tested against a larger repo pool

---

## Limitations

- Language byte counts reflect file size, not importance, so a repo can
  look skewed toward a language with large generated files.
- "Good first issue" labels are a convention, not a guarantee; the LLM step
  partly compensates by reading the actual issue title and labels rather
  than trusting the label alone.
- Difficulty scoring currently relies on title and labels only — the issue
  body isn't sent to the LLM yet, which limits how much context it has.
- Resource/difficulty scoring could incorporate more signals (merge rate,
  maintainer responsiveness, docs quality).

---

## License

MIT