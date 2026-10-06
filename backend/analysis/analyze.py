import os
import json
import pandas as pd
from sqlalchemy import text
from analysis.llm_client import ask_gemini

from concurrent.futures import ThreadPoolExecutor, as_completed

# Path relative to THIS file, so it works regardless of working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_PATH = os.path.join(BASE_DIR, "..", "db", "update_repo_analysis.sql")
with open(SQL_PATH) as f:
    INSERT_SQL = text(f.read())


def analyze_issue(title, body, labels, language):
    prompt = f"""You are assessing GitHub issues to help match beginner developers to suitable open-source contributions.

Analyze the issue below and respond with ONLY a valid JSON object — no markdown, no code fences, no explanation outside the JSON.

The JSON must have exactly these keys:
{{
  "level": "beginner" | "intermediate" | "advanced",
  "skills": ["skill1", "skill2"],
  "estimated_hours": <number>,
  "reasoning": "<one concise sentence>"
}}

Guidelines:
- "level": how much experience a contributor needs. "beginner" = clear scope, well-defined, minimal codebase knowledge needed. "intermediate" = requires understanding multiple components. "advanced" = deep architectural knowledge or complex changes.
- "skills": 1-4 specific technical skills the issue exercises (e.g. "{language}", "testing", "API design").
- "estimated_hours": rough time estimate for someone at the assessed level.
- "reasoning": one sentence on why you assigned this level.

Issue title: {title}
Issue body: {body}
Labels: {labels}
Primary language: {language}

Respond with the JSON object only."""
    return prompt


def get_issues_to_analyze(engine, language, min_pct=30):
    """Pull open issues from repos where the language meets the threshold,
    skipping any issue already analysed (caching)."""
    query = """
        WITH repo_totals AS (
            SELECT repo_id, SUM(bytes) AS total_bytes
            FROM repo_languages GROUP BY repo_id
        )
        SELECT i.repo_id,
               i.issue_number,
               i.title,
               i.labels,
               r.full_name
        FROM repo_issues i
        JOIN repositories r   ON r.id = i.repo_id
        JOIN repo_languages l ON l.repo_id = i.repo_id
        JOIN repo_totals t    ON t.repo_id = i.repo_id
        WHERE i.state = 'open'
          AND l.language = %(language)s
          AND (100.0 * l.bytes / t.total_bytes) >= %(min_pct)s
          AND NOT EXISTS (
              SELECT 1 FROM repo_analysis a
              WHERE a.repo_id = i.repo_id
                AND a.issue_number = i.issue_number
          )
    """
    return pd.read_sql(query, engine,
                       params={"language": language, "min_pct": min_pct})


def save_analysis(engine, repo_id, issue_number, level, reasoning):
    with engine.begin() as conn:
        conn.execute(INSERT_SQL, {
            "repo_id": repo_id,
            "issue_number": issue_number,
            "level": level,
            "reasoning": reasoning
        })




def process_issue(engine, row, language):
    """Does the full unit of work for one issue — this is what gets threaded."""
    prompt = analyze_issue(row["title"], "", row["labels"], language)
    raw = ask_gemini(prompt)
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(cleaned)
    save_analysis(engine, row["repo_id"], row["issue_number"],
                  result["level"], result["reasoning"])
    return row["full_name"], row["issue_number"], result["level"]


def run_analysis(engine, language, rows=3):
    issues = get_issues_to_analyze(engine, language)
    print(f"Found {len(issues)} un-analysed issues; processing {rows}")

    batch = issues.head(rows)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(process_issue, engine, row, language): row
            for _, row in batch.iterrows()
        }

        for future in as_completed(futures):
            row = futures[future]
            try:
                full_name, issue_number, level = future.result()
                print(f"  {full_name} #{issue_number}: {level}")
            except Exception as e:
                print(f"  Failed on #{row['issue_number']}: {e}")