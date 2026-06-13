import requests
from bs4 import BeautifulSoup

def search_dwp_uk(query="data engineer", limit=10):
    url = f"https://findajob.dwp.gov.uk/search?q={query.replace(' ', '+')}&loc=86383"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return f"DWP error (HTTP {resp.status_code})"
        soup = BeautifulSoup(resp.content, "html.parser")
        jobs = soup.find_all("div", class_="search-result")
        if not jobs:
            return "No jobs found on DWP Find a Job."
        output = f"DWP Find a Job (UK): {len(jobs)} results\n"
        for job in jobs[:limit]:
            title_el = job.find("a", class_="govuk-link")
            title = title_el.text.strip() if title_el else "N/A"
            company_el = job.find("strong")
            company = company_el.text.strip() if company_el else "N/A"
            loc_el = job.find("span")
            loc = loc_el.text.strip() if loc_el else ""
            output += f"- {title} @ {company} ({loc})\n"
        return output
    except Exception as e:
        return f"DWP error: {e}"
