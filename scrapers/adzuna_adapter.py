import os
import random
import requests

def search_adzuna(keyword, page=1):
    app_id = os.environ.get("ADZUNA_APP_ID")
    if not app_id:
        return "Adzuna App ID not configured."
    adzuna_keys = []
    for i in range(1, 5):
        key = os.environ.get(f"ADZUNA_API_KEY_{i}")
        if key:
            adzuna_keys.append(key)
    if not adzuna_keys:
        return "No Adzuna API keys configured."
    random.shuffle(adzuna_keys)
    last_error = None
    for api_key in adzuna_keys:
        url = f"https://api.adzuna.com/v1/api/jobs/za/search/{page}"
        params = {"app_id": app_id, "app_key": api_key, "results_per_page": 5, "what": keyword, "content-type": "application/json"}
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("results", [])
                if not jobs:
                    return f"No Adzuna jobs found for '{keyword}'."
                output = f"Adzuna (ZA): {len(jobs)} jobs for '{keyword}':\n"
                for job in jobs[:5]:
                    title = job.get("title", "N/A")
                    company = job.get("company", {}).get("display_name", "N/A")
                    location = job.get("location", {}).get("display_name", "")
                    redirect_url = job.get("redirect_url", "#")
                    output += f"- {title}\n  {company} – {location}\n  Apply: {redirect_url}\n"
                return output
            else:
                last_error = f"HTTP {resp.status_code}"
                continue
        except Exception as e:
            last_error = str(e)
            continue
    return f"Adzuna error: {last_error}"
