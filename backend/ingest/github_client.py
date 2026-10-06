import os
from dotenv import load_dotenv
import requests
import json
from datetime import date

load_dotenv()
api_key = os.getenv("GITHUB_TOKEN")
print("Token loaded:", api_key is not None)

header = {"Authorization": f"token {api_key}"}
SEARCH_URL = "https://api.github.com/search/repositories"


def passes_threshold(repo):
    return (
        int(repo["stargazers_count"]) >= 10 and
        int(repo["forks_count"]) >= 2 and
        int(repo["open_issues_count"]) >= 1
    )


def is_false(repo):
    # fixed: compare to real booleans, not the strings "false"/"true"
    return repo["archived"] is False and repo["disabled"] is False


def is_true(repo):
    return repo["has_issues"] is True and repo["has_projects"] is True


def keep(repo):
    """Single source of truth for 'should this repo survive filtering' —
    confirm this AND logic matches your intent: quality threshold AND usable state."""
    return passes_threshold(repo) and is_false(repo) and is_true(repo)



def get_total_count(start, end, language=None):
    """Cheap, 1-result request — just reads total_count for a window."""
    query = f"created:{start.isoformat()}..{end.isoformat()}"
    if language:
        query += f" language:{language}"
    response = requests.get(SEARCH_URL, headers=header, params={"q": query, "per_page": 1})
    data = response.json()
    if not isinstance(data, dict) or "total_count" not in data:
        raise RuntimeError(f"Unexpected GitHub API response: {data}")
    return data["total_count"]


import time

def get_total_count(start, end, language=None):
    time.sleep(1)
    query = f"created:{start.isoformat()}..{end.isoformat()}"
    if language:
        query += f" language:{language}"
    response = requests.get(SEARCH_URL, headers=header, params={"q": query, "per_page": 1})
    data = response.json()
    if not isinstance(data, dict) or "total_count" not in data:
        raise RuntimeError(f"Unexpected GitHub API response: {data}")
    return data["total_count"]


def fetch_window(start, end, total, language=None):
    query = f"created:{start.isoformat()}..{end.isoformat()}"
    if language:
        query += f" language:{language}"

    collected, page = [], 1
    while len(collected) < total:
        time.sleep(5)
        response = requests.get(SEARCH_URL, headers=header,
                                 params={"q": query, "per_page": 100, "page": page})
        data = response.json()
        if not isinstance(data, dict) or "items" not in data:
            raise RuntimeError(f"Unexpected GitHub API response: {data}")
        items = data["items"]
        if not items:
            break

        collected.extend([r for r in items if keep(r)])
        page += 1

    return collected


def extract_range(start, end, language=None, target=10000):
    """Adaptive bisection: subdivides [start, end] so no single query
    exceeds GitHub's 1000-result cap. Returns a flat, filtered list."""
    repos = []
    pending = [(start, end)]

    while pending and len(repos) < target:
        window_start, window_end = pending.pop()

        total = int(get_total_count(window_start, window_end, language))
        if total == 0:
            continue

        if (window_end - window_start).days < 1:
            print(f"  WARNING: {window_start}..{window_end} has {total} repos "
                f"and can't be split further — some will be missed")
            repos.extend(fetch_window(window_start, window_end, total, language))
                
        else:
            window_repos = fetch_window(window_start, window_end, total, language)
            repos.extend(window_repos)
            print(f"  {window_start}..{window_end}: {total} repos "
                  f"(total collected: {len(repos)})")

    return repos



def extract(start, end, file, language=None, target=10000):
    """Drop-in replacement for the old extract(url, file): same write-then-read-back
    contract, now backed by extract_range instead of a single raw request."""
    repos = extract_range(start, end, language=language, target=target)

    with open(f"data/raw/{file}", "w") as f:
        json.dump(repos, f, indent=2)

    with open(f"data/raw/{file}", "r") as f:
        return json.load(f)

