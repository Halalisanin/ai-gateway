import os
import sys
import subprocess
import json

JSCRAPER_REPOS = "/home/liviyo/Documents/job/jScraper_repos"

def run_local_scraper(repo_name, script_path, *args):
    full_path = os.path.join(JSCRAPER_REPOS, repo_name, script_path)
    if not os.path.exists(full_path):
        return f"Script not found: {full_path}"
    try:
        result = subprocess.run(
            [sys.executable, full_path] + list(args),
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONPATH": os.path.dirname(full_path)}
        )
        output = result.stdout.strip() or result.stderr.strip()
        return f"Local scraper ({repo_name}):\n{output[:2000]}"
    except subprocess.TimeoutExpired:
        return f"Local scraper ({repo_name}) timed out"
    except Exception as e:
        return f"Local scraper ({repo_name}) error: {e}"

def run_techconnect_extract():
    return run_local_scraper("techConnect_jobs_ETL_pipeline", "etl/extract_all.py")

def run_jooble_local(keyword="", country="us"):
    return run_local_scraper("jooble-scraper", "jooble.py", "-s", keyword, "-c", country, "-x")

SCRAPER_HELP = {
    "techconnect": "UK DWP Find a Job pipeline via techConnect_jobs_ETL_pipeline",
    "jooble": "Jooble scraper (run_local_scraper('jooble-scraper', 'jooble.py', '-s', '<keyword>', '-c', '<country>', '-x'))",
}
