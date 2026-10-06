# main.py
from sqlalchemy import create_engine
from ingest import github_client ,load,transform,narrow
import os
import json
from dotenv import load_dotenv
from analysis.analyze import run_analysis
from db.repo_analysis import create_repo_analysis_table

from datetime import date

def pipeline():
    
    load_dotenv()
    api_key = os.getenv("GITHUB_TOKEN")
    print("Token loaded:", api_key is not None)

    header = {"Authorization": f"token {api_key}"}
    engine = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/repo_finder")
    url = "https://api.github.com/search/repositories?q=created:>2025-01-01+stars:>10+good-first-issues:>1&sort=updated&per_page=100"
    
    github_client.extract( start=date(2015, 1, 1),   # earliest repo creation date you care about
    end=date.today(),file="github_repodata.json")
    df = transform.transform()
    load.load(engine,df)
    
    with open("data/raw/github_repodata.json", "r") as f:
        repos = json.load(f)
    narrow.enrich_and_build_tables(engine, repos, header)
    # create_repo_analysis_table()
    # narrow.enrich_and_build_tables(engine,repos,header)
    run_analysis(engine,"Python")

