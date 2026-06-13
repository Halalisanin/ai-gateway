import json
import urllib3

http = urllib3.PoolManager()

def search_jooble(keyword="", location=None, country="us", limit=10):
    try:
        url = f"https://{country}.jooble.org/api/serp/jobs"
        form_data = {"search": keyword}
        if location:
            form_data["location"] = location
        encoded = json.dumps(form_data).encode("utf-8")
        resp = http.request("POST", url, body=encoded, headers={"Content-Type": "application/json"})
        if resp.status != 200:
            return f"Jooble error (HTTP {resp.status}) — the free endpoint may be blocked. Try source=jobhive or source=dwp instead."
        data = json.loads(resp.data)
        jobs = data.get("jobs", [])
        if not jobs:
            return "No jobs found on Jooble."
        output = f"Jooble ({country}): {len(jobs)} jobs\n"
        for job in jobs[:limit]:
            title = job.get("position", "N/A")
            co = job.get("company", {})
            company = co.get("name", "N/A") if isinstance(co, dict) else str(co)
            loc = job.get("location", "")
            if isinstance(loc, dict):
                loc = loc.get("city", loc.get("country", ""))
            output += f"- {title} @ {company} ({loc})\n"
        return output
    except Exception as e:
        return f"Jooble error: {e}"
