#!/usr/bin/env python3
from flask import Flask, request, jsonify
import os, sys, requests, re, json
import pandas as pd
from datetime import datetime, timedelta
from serpapi import GoogleSearch

sys.path.append('/home/liviyo/lib')
from memory_store import init_db, get_recent_context, add_message
from knowledge_base import kb
from gbrain_client import search as gbrain_search, query as gbrain_query, save_page as gbrain_save, stats as gbrain_stats
from gstack_wrapper import run_review, run_spec, run_qa, run_health, available_tools as gstack_list
from wrappers_21st import handle_command as handle_21st, list_available as list_21st_tools
import obsidian_sync

init_db()
obsidian_sync.start_watcher()
obsidian_sync.sync_all()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

# API Keys
GROQ_KEY = os.environ.get('GROQ_API_KEY')
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY')
GEMINI_KEY = os.environ.get('GEMINI_API_KEY')
SERPAPI_KEY = os.environ.get('SERPAPI_API_KEY')
NEWSAPI_KEY = os.environ.get('NEWSAPI_API_KEY')
GNEWS_KEY = os.environ.get('GNEWS_API_KEY') or 'e9d8c864ad15fe43777b7b2f1ae9b100'
RAPIDAP_KEY = os.environ.get('RAPIDAPI_API_KEY') or '76335f870amsh774a40aff039773p1b1f8cjsn0cf4d650c092'
ADZUNA_APP_ID = os.environ.get('ADZUNA_APP_ID')
single_key = os.environ.get('ADZUNA_API_KEY')
ADZUNA_KEYS = [os.environ.get(f'ADZUNA_API_KEY_{i}') for i in range(1, 5) if os.environ.get(f'ADZUNA_API_KEY_{i}')]
if single_key and single_key not in ADZUNA_KEYS:
    ADZUNA_KEYS.append(single_key)

# Hugging Face keys (10)
hf_keys = []
for i in range(1, 11):
    key = os.environ.get(f'HF_API_KEY_{i}')
    if key:
        hf_keys.append(key)
current_hf_index = 0

# ---------- Provider helpers ----------
def call_groq(messages):
    if not GROQ_KEY:
        raise Exception("Groq key not set")
    resp = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': f'Bearer {GROQ_KEY}', 'Content-Type': 'application/json'},
        json={'model': 'llama-3.3-70b-versatile', 'messages': messages, 'max_tokens': 600},
        timeout=15
    )
    if resp.status_code != 200:
        raise Exception(f"Groq error {resp.status_code}")
    return resp.json()['choices'][0]['message']['content']

def call_openrouter(messages):
    if not OPENROUTER_KEY:
        raise Exception("OpenRouter key not set")
    models = [
        'openrouter/free',
        'meta-llama/llama-3.3-70b-instruct:free',
        'qwen/qwen3-coder:free'
    ]
    for model in models:
        try:
            resp = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': f'Bearer {OPENROUTER_KEY}', 'Content-Type': 'application/json'},
                json={'model': model, 'messages': messages, 'max_tokens': 600},
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
        except:
            continue
    raise Exception("All OpenRouter models failed")

def call_gemini(messages):
    if not GEMINI_KEY:
        raise Exception("Gemini key not set")
    prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    resp = requests.post(url, json={'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': 600}}, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"Gemini error {resp.status_code}")
    return resp.json()['candidates'][0]['content']['parts'][0]['text']

def call_huggingface(messages):
    global current_hf_index
    if not hf_keys:
        raise Exception("No HF keys available")
    prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    for attempt in range(len(hf_keys) * 2):
        key = hf_keys[current_hf_index % len(hf_keys)]
        current_hf_index += 1
        try:
            resp = requests.post(
                'https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3',
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json={'inputs': prompt, 'parameters': {'max_new_tokens': 600}},
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()[0]['generated_text'].strip()
            elif resp.status_code in (401, 429):
                continue
        except:
            continue
    raise Exception("All HF keys exhausted")

# ---------- Tools ----------

def _orgupdate_jobs(source, keyword, location="", country=""):
    """Shared function for Reed, WTTJ, ZipRecruiter via orgupdate API."""
    params = {"source": source, "pagesToFetch": 1, "isFreeUser": True}
    if location:
        params["locationName"] = location
    if country:
        params["countryName"] = country
    try:
        resp = requests.post("https://api.orgupdate.com/search-jobs-v1", json=params, timeout=15)
        if resp.status_code != 200:
            return f"{source} API error: HTTP {resp.status_code}"
        data = resp.json()
        if not data:
            return f"No jobs found from {source}."
        # Filter client-side since includeKeyword doesn't work for all sources
        if keyword:
            kw = keyword.lower()
            data = [j for j in data if kw in (j.get("job_title", j.get("title", ""))).lower()
                    or kw in (j.get("company_name", "")).lower()]
        if not data:
            return f"No {source} jobs found for '{keyword}'."
        output = f"Jobs from {source}"
        if keyword:
            output += f" for '{keyword}'"
        output += ":\n"
        for j in data[:5]:
            title = j.get("job_title", j.get("title", "No title"))
            company = j.get("company_name", "Unknown")
            loc = j.get("location", "")
            salary = j.get("salary", "")
            url = j.get("URL", j.get("url", ""))
            output += f"- {title}\n  {company} - {loc} | {salary}\n  {url}\n"
        return output
    except Exception as e:
        return f"{source} error: {e}"

def get_reed_jobs(keyword, location="", country="GB"):
    return _orgupdate_jobs("reed", keyword, location, country)

def get_ziprecruiter_jobs(keyword, location="", country="US"):
    return _orgupdate_jobs("ziprecruiter", keyword, location, country)

def get_wttj_jobs(keyword, location="", country="FR"):
    return _orgupdate_jobs("welcometothejungle", keyword, location, country)

def get_dwp_jobs(keyword):
    """Scrape UK DWP Find a Job for listings."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return "DWP scraper requires BeautifulSoup. Run: pip3 install beautifulsoup4"
    url = f"https://findajob.dwp.gov.uk/search?q={keyword}&loc=86383"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return f"DWP error: HTTP {resp.status_code}"
        soup = BeautifulSoup(resp.content, "html.parser")
        jobs = soup.find_all("div", class_="search-result")
        if not jobs:
            return f"No DWP jobs found for '{keyword}'."
        output = f"UK DWP jobs for '{keyword}':\n"
        for job in jobs[:5]:
            title_el = job.find("a", class_="govuk-link")
            title = title_el.text.strip() if title_el else "No title"
            link = title_el["href"] if title_el and title_el.get("href") else ""
            if link and not link.startswith("http"):
                link = "https://findajob.dwp.gov.uk" + link
            company_el = job.find("strong")
            company = company_el.text.strip() if company_el else "Unknown"
            loc_el = job.find("span")
            loc = loc_el.text.strip() if loc_el else ""
            output += f"- {title}\n  {company} - {loc}\n  {link}\n"
        return output
    except Exception as e:
        return f"DWP error: {e}"

def get_jobhive_jobs(keyword, limit=5):
    """Search small ATS parquet files from jobhive (under ~5MB each)."""
    import io, time
    t0 = time.time()
    manifest_url = "https://storage.stapply.ai/jobhive/v1/manifest.json"
    try:
        mresp = requests.get(manifest_url, timeout=30)
        if mresp.status_code != 200:
            return f"Jobhive manifest error: HTTP {mresp.status_code}"
        manifest = mresp.json()
    except Exception as e:
        return f"Jobhive manifest error: {e}"

    # Only download small ATS files (under 5MB) for speed
    small_atss = []
    for ats, info in manifest.get("by_ats", {}).items():
        sz = info.get("parquet_size_bytes", 0)
        if sz < 5_000_000:  # under 5MB
            small_atss.append((ats, info, sz))
    small_atss.sort(key=lambda x: x[2])  # smallest first

    results = []
    searched = 0
    for ats, entry, _ in small_atss:
        if len(results) >= limit:
            break
        url = entry.get("parquet")
        if not url:
            continue
        try:
            presp = requests.get(url, timeout=30)
            if presp.status_code != 200:
                continue
            searched += 1
            df = pd.read_parquet(io.BytesIO(presp.content))
            if "title" not in df.columns:
                continue
            mask = df["title"].str.contains(keyword, case=False, na=False)
            matches = df[mask]
            for _, row in matches.iterrows():
                results.append({
                    "title": row.get("title", row.get("job_title", "")),
                    "company": row.get("company", ""),
                    "location": row.get("location", ""),
                    "salary": row.get("salary_summary", ""),
                    "ats": ats,
                })
                if len(results) >= limit:
                    break
        except Exception:
            continue
    elapsed = time.time() - t0
    if not results:
        return f"No jobhive jobs found for '{keyword}' (searched {searched} small ATS in {elapsed:.1f}s)."
    output = f"Jobhive jobs for '{keyword}' ({elapsed:.1f}s, {searched} ATS):\n"
    for j in results[:limit]:
        output += f"- {j['title']}\n  {j['company']} - {j['location']} | {j['salary']} [{j['ats']}]\n"
    return output

def get_weather(city):
    try:
        r = requests.get(f"https://wttr.in/{city}?format=%C+%t+%w+%h", timeout=10)
        return f"Weather in {city}: {r.text.strip()}" if r.status_code == 200 else f"Weather unavailable for {city}"
    except:
        return "Weather error"

def get_news(query):
    if NEWSAPI_KEY:
        try:
            r = requests.get(f"https://newsapi.org/v2/everything?q={query}&apiKey={NEWSAPI_KEY}&pageSize=3", timeout=10)
            if r.status_code == 200:
                articles = r.json().get("articles", [])
                if articles:
                    return "News:\n" + "\n".join([f"-  {a['title']} ({a['source']['name']})" for a in articles[:3]])
        except:
            pass
    return f"Could not fetch news for '{query}'."

def scan_folder(path):
    import os
    if not os.path.exists(path): return f"Error: Path '{path}' does not exist."
    if not os.path.isdir(path): return f"Error: '{path}' is not a directory."
    summary = []
    max_bytes = 30000
    current = 0
    file_count = 0
    for root, dirs, files in os.walk(path):
        depth = root[len(path):].count(os.sep)
        if depth > 2: continue
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', 'venv', 'env')]
        for file in files:
            if file_count >= 10:
                summary.append("\n... (more files, limit reached)")
                break
            if file.endswith(('.py','.js','.ts','.json','.md','.txt','.html','.css','.yaml','.yml')):
                full = os.path.join(root, file)
                rel = os.path.relpath(full, path)
                try:
                    with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(2000)
                    entry = f"\n--- {rel} ---\n{content}\n"
                    if current + len(entry) > max_bytes:
                        summary.append("\n... (truncated)")
                        break
                    summary.append(entry)
                    current += len(entry)
                    file_count += 1
                except:
                    summary.append(f"\n--- {rel} --- [unreadable]\n")
        if current >= max_bytes or file_count >= 10: break
    result = "".join(summary) if summary else "No readable files found."
    return f"Folder analysis for {path}:\n{result}"

def get_tenders(query=None, page=1):
    url = "https://ocds-api.etenders.gov.za/api/OCDSReleases"
    date_to = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    params = {"PageNumber": page, "PageSize": 10, "dateFrom": date_from, "dateTo": date_to}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return f"Tenders API error (HTTP {resp.status_code})"
        data = resp.json()
        releases = data.get("releases", [])
        if not releases:
            return "No tenders found in the last 90 days."
        filtered = releases
        if query:
            qlower = query.lower()
            filtered = [r for r in releases if qlower in r.get("tender", {}).get("title", "").lower()]
        if not filtered:
            return f"No tenders matching '{query}'."
        output = f"Tenders (page {page})"
        if query:
            output += f" matching '{query}'"
        output += ":\n"
        for r in filtered[:5]:
            tender = r.get("tender", {})
            title = tender.get("title", "No title")
            procuring = tender.get("procuringEntity", {}).get("name", "Unknown")
            deadline = tender.get("tenderPeriod", {}).get("endDate", "Unknown")
            output += f"- {title}\n  Procuring: {procuring}\n  Deadline: {deadline}\n"
        return output
    except requests.exceptions.Timeout:
        return "Tenders API timed out."
    except Exception as e:
        return f"Tenders error: {e}"

def get_adzuna_jobs(keyword, page=1):
    if not ADZUNA_APP_ID:
        return "Adzuna App ID not configured."
    if not ADZUNA_KEYS:
        return "No Adzuna API keys configured."
    # Parse location out of the query string (e.g. "BPO in Johannesburg" -> what="BPO", where="Johannesburg")
    what = keyword
    where = ""
    import re as _re
    loc_match = _re.search(r'\b(in|at|near|around)\s+(.+)$', keyword, _re.IGNORECASE)
    if loc_match:
        what = keyword[:loc_match.start()].strip()
        where = loc_match.group(2).strip()
    # Also strip words like "jobs", "hiring", "openings" from what
    what = _re.sub(r'\b(jobs?|hiring|openings|vacancies?|positions?)\b', '', what, flags=_re.IGNORECASE).strip()
    if not what:
        what = keyword  # fallback to original
    for api_key in ADZUNA_KEYS:
        url = f"https://api.adzuna.com/v1/api/jobs/za/search/{page}"
        params = {"app_id": ADZUNA_APP_ID, "app_key": api_key, "results_per_page": 5, "what": what, "content-type": "application/json"}
        if where:
            params["where"] = where
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("results", [])
                if not jobs: continue
                output = f"Job listings for '{what}'"
                if where:
                    output += f" in '{where}'"
                output += ":\n"
                for j in jobs[:5]:
                    title = j.get("title", "No title")
                    company = j.get("company", {}).get("display_name", "Unknown")
                    location = j.get("location", {}).get("display_name", "")
                    apply_url = j.get("redirect_url", "#")
                    output += f"- {title}\n  {company} - {location}\n  Apply: {apply_url}\n"
                return output
            else:
                continue
        except:
            continue
    return f"Adzuna: no results for '{keyword}'."

def get_gnews(k):
    if not GNEWS_KEY: return "GNews API key missing."
    url = "https://gnews.io/api/v4/search"
    params = {"q": k, "token": GNEWS_KEY, "lang": "en", "max": 5}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            articles = data.get("articles", [])
            if not articles: return f"No news for '{k}'."
            output = f"News for '{k}':\n"
            for a in articles[:5]:
                title = a.get("title", "No title")
                source = a.get("source", {}).get("name", "Unknown")
                pub = a.get("publishedAt", "")[:10]
                output += f"- {title} ({source} {pub})\n"
            return output
        else:
            return f"Gnews error: HTTP {resp.status_code}"
    except Exception as e:
        return f"Gnews error: {e}"

def get_rapidjobs(q):
    if not RAPIDAP_KEY: return "RapidAPI key missing."
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {"X-RapidAPI-Key": RAPIDAP_KEY, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
    params = {"query": q, "page": 1, "num_pages": 1}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            jobs = data.get("data", [])
            if not jobs: return f"No jobs for '{q}'."
            output = f"Job listings for '{q}':\n"
            for j in jobs[:5]:
                title = j.get("job_title", "No title")
                company = j.get("employer_name", "Unknown")
                location = j.get("job_city", "") or j.get("job_state", "")
                apply_url = j.get("job_apply_link", "#")
                output += f"- {title}\n  {company} - {location}\n  Apply: {apply_url}\n"
            return output
        else:
            return f"RapidJobs error: HTTP {resp.status_code}"
    except Exception as e:
        return f"RapidJobs error: {e}"

def perform_search(query):
    if not SERPAPI_KEY:
        return "[Error: SerpAPI key not set]"
    params = {"q": query, "api_key": SERPAPI_KEY, "engine": "google", "num": 3}
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        organic = results.get("organic_results", [])
        if not organic:
            return f"No results found for '{query}'."
        output = f"Search results for '{query}':\n"
        for i, r in enumerate(organic[:3], 1):
            output += f"{i}. {r.get('title', '')}\n   {r.get('snippet', '')}\n   Link: {r.get('link', '')}\n"
        return output
    except Exception as e:
        return f"Search error: {e}"

# ---------- Tool dispatcher ----------

def post_to_facebook(message):
    token = os.environ.get("FACEBOOK_PAGE_TOKEN")
    if not token:
        return "❌ Facebook token missing. Add FACEBOOK_PAGE_TOKEN to env."
    page_id = os.environ.get("FACEBOOK_PAGE_ID", "me")
    url = f"https://graph.facebook.com/v18.0/{page_id}/feed"
    params = {"message": message, "access_token": token}
    try:
        resp = requests.post(url, params=params, timeout=15)
        if resp.status_code == 200:
            return f"✅ Posted to Facebook. Post ID: {resp.json().get('id', 'unknown')}"
        else:
            err = resp.json().get("error", {}).get("message", "Unknown error")
            return f"❌ Facebook error: {err}"
    except Exception as e:
        return f"❌ Facebook error: {e}"

def post_to_twitter(message):
    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        return "❌ Missing requests_oauthlib. Run: pip3 install requests-oauthlib"
    ck = os.environ.get("TWITTER_CONSUMER_KEY")
    cs = os.environ.get("TWITTER_CONSUMER_SECRET")
    at = os.environ.get("TWITTER_ACCESS_TOKEN")
    ats = os.environ.get("TWITTER_ACCESS_SECRET")
    if not all([ck, cs, at, ats]):
        return "❌ Twitter credentials incomplete. Check your 4 keys."
    url = "https://api.twitter.com/2/tweets"
    auth = OAuth1(ck, cs, at, ats)
    payload = {"text": message[:280]}
    try:
        resp = requests.post(url, json=payload, auth=auth, timeout=15)
        if resp.status_code == 201:
            return f"✅ Posted to Twitter. Tweet ID: {resp.json().get('data', {}).get('id', 'unknown')}"
        else:
            return f"❌ Twitter error: {resp.json().get('title', 'Unknown')} (HTTP {resp.status_code})"
    except Exception as e:
        return f"❌ Twitter error: {e}"

def post_to_linkedin(message):
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token:
        return ("❌ LinkedIn access token missing. After creating your app, generate a token "
                "with 'w_member_social' scope using the LinkedIn OAuth 2.0 tool. "
                "Then add LINKEDIN_ACCESS_TOKEN to /etc/ai-gateway/env")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Get person ID
        resp = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=10)
        if resp.status_code != 200:
            return f"❌ LinkedIn auth error: {resp.json().get('message', '')}"
        person_id = resp.json().get("sub")
        # Post a share
        payload = {
            "author": f"urn:li:person:{person_id}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": message[:700]},
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
        }
        resp = requests.post("https://api.linkedin.com/v2/ugcPosts", json=payload, headers=headers, timeout=15)
        if resp.status_code == 201:
            return f"✅ Posted to LinkedIn. Share ID: {resp.json().get('id', 'unknown')}"
        else:
            return f"❌ LinkedIn error: {resp.json().get('message', 'Unknown error')}"
    except Exception as e:
        return f"❌ LinkedIn error: {e}"

def post_to_tiktok(message):
    return "ℹ️ TikTok API does not support text-only posts. For video posts, use [TIKTOK_VIDEO: path, description]"


# ---------- KB (Knowledge Base / RAG) ----------
def kb_search(query):
    return kb.search(query)

def kb_index(path):
    return kb.index_file(path)

def kb_stats():
    return kb.stats()

# ---------- Memory (gbrain) ----------
def memory_search(query):
    return gbrain_search(query)

def memory_query(question):
    return gbrain_query(question)

def memory_save(slug, content):
    return gbrain_save(slug, content)

def memory_stats():
    return gbrain_stats()

# ---------- GSTACK ----------
def gstack_review(path):
    return run_review(path)

def gstack_spec(desc):
    return run_spec(desc)

def gstack_health():
    return run_health()

def gstack_tools():
    return gstack_list()

def handle_tool(command):
    m = re.match(r'\[(?:TOOL:\s*)?(\w+)[:\s]\s*(.*?)\]', command, re.IGNORECASE)
    if not m: return None
    tool, arg = m.group(1).lower(), m.group(2).strip()
    if tool == 'weather': return get_weather(arg)
    if tool == 'search':  return perform_search(arg)
    if tool == 'news':    return get_news(arg)
    if tool == 'scan':    return scan_folder(arg)
    if tool == 'tenders': return get_tenders(arg if arg else None)
    if tool == 'jobs':    return get_adzuna_jobs(arg)
    if tool == 'gnews':   return get_gnews(arg)
    if tool == 'rapidjobs': return get_rapidjobs(arg)
    if tool == 'reed':      return get_reed_jobs(arg)
    if tool == 'ziprecruiter': return get_ziprecruiter_jobs(arg)
    if tool == 'wttj':      return get_wttj_jobs(arg)
    if tool == 'dwp':       return get_dwp_jobs(arg)
    if tool == 'jobhive':   return get_jobhive_jobs(arg)

    if tool == 'knowledge':   return kb_search(arg)
    if tool == 'kb':          return kb_search(arg)
    if tool == 'know_index':  return kb_index(arg)
    if tool == 'kb_index':    return kb_index(arg)
    if tool == 'kb_stats':    return kb_stats()

    if tool == 'memory':    return memory_search(arg)
    if tool == 'mem_q':     return memory_query(arg)
    if tool == 'mem_save':
        parts = arg.split('|', 1)
        slug = parts[0].strip()
        content = parts[1].strip() if len(parts) > 1 else arg
        return memory_save(slug, content)
    if tool == 'mem_stats': return memory_stats()

    if tool == 'gstack_review': return gstack_review(arg)
    if tool == 'gstack_spec':   return gstack_spec(arg)
    if tool == 'gstack_health': return gstack_health()
    if tool == 'gstack_tools':  return gstack_tools()
    if tool == 'gstack_qa':     return run_qa(arg)

    if tool in ('21st', 'ui', '21st_dev'):
        return handle_21st(arg)

    if tool == 'obsidian':
        return obsidian_sync.handle_command(arg)

    if tool == 'facebook':
        return post_to_facebook(arg)
    if tool == 'twitter':
        return post_to_twitter(arg)
    if tool == 'linkedin':
        return post_to_linkedin(arg)
    if tool == 'tiktok':
        return post_to_tiktok(arg)
    return f"Unknown tool: {tool}"

# ---------- Routes ----------
@app.route('/search', methods=['POST'])
def search_web():
    data = request.json
    query = data.get('query')
    if not query:
        return jsonify({'error': 'Missing "query" parameter'}), 400
    if not SERPAPI_KEY:
        return jsonify({'error': 'SerpAPI key not configured'}), 500
    params = {"q": query, "api_key": SERPAPI_KEY, "engine": "google", "hl": "en", "num": 5}
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        organic = results.get("organic_results", [])
        simplified = [{"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")} for r in organic[:5]]
        return jsonify({"query": query, "results": simplified})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/chat/completions', methods=['POST'])
def chat():
    session_id = request.headers.get('X-Session-Id', 'default')
    user_msg = request.json.get('messages', [{"role": "user", "content": ""}])[0].get('content')
    if not user_msg:
        return jsonify({'error': 'No user message'}), 400

    trimmed = user_msg.strip().upper()

    # Direct tools (bypass LLM)
    direct_match = re.match(r'\[(WEATHER|NEWS|GNEWS|SEARCH|SCAN|TENDERS|JOBS|RAPIDJOBS|REED|ZIPRECRUITER|WTTJ|DWP|JOBHIVE|FACEBOOK|TWITTER|LINKEDIN|TIKTOK|OBSIDIAN|KNOWLEDGE|KNOW_INDEX|KB|KB_INDEX|KB_STATS|MEMORY|MEM_Q|MEM_SAVE|MEM_STATS|GSTACK_REVIEW|GSTACK_SPEC|GSTACK_HEALTH|GSTACK_TOOLS|GSTACK_QA|21ST|UI|21ST_DEV)[:\s]\s*(.*?)\]', user_msg, re.IGNORECASE)
    if direct_match:
        tool, arg = direct_match.group(1).upper(), direct_match.group(2).strip()
        result = handle_tool(f"[{tool}: {arg}]")
        return jsonify({'choices': [{'message': {'role': 'assistant', 'content': result}}]})

    # LLM request
    context = get_recent_context(session_id, n=5)
    messages = [{'role': r, 'content': c} for r, c in context]
    messages.append({'role': 'user', 'content': user_msg})
    messages.insert(0, {'role': 'system', 'content': (
        "You have tools. Before answering any factual question, you MUST call the right tool. "
        "To call a tool, write exactly [TOOL: argument]. "
        "Valid tools: WEATHER GNEWS SEARCH SCAN TENDERS JOBS RAPIDJOBS "
        "ZIPRECRUITER REED WTTJ DWP JOBHIVE. "
        "For news use GNEWS, not NEWS. Once the tool returns, give the user your final answer. "
        "CRITICAL: When using JOBS or job tools, use a SHORT keyword, NOT the full user query. "
        "E.g. 'BPO jobs in London' -> [JOBS: BPO in London]. "
        "E.g. 'Software Engineer jobs' -> [JOBS: Software Engineer]. "
        "--- NEW TOOLS --- "
        "[KNOWLEDGE: question] searches indexed documents (RAG). "
        "[KNOW_INDEX: path] indexes a file or folder into the knowledge base. "
        "[MEMORY: query] searches persistent long-term memory (gbrain). "
        "[MEM_Q: question] asks the brain with hybrid search. "
        "[MEM_SAVE: slug | content] saves info to long-term memory. "
        "[MEM_STATS: ] shows memory stats. "
        "[GSTACK_REVIEW: path] reviews code using gstack. "
        "[GSTACK_SPEC: idea] generates a spec using gstack. "
        "[GSTACK_HEALTH: ] checks gstack platform health. "
        "[GSTACK_TOOLS: ] lists available gstack tools. "
        "--- 21st.dev UI TOOLS --- "
        "[21ST: list] shows available 21st.dev UI component tools. "
        "[21ST: create_ui|prompt|search|file|project] builds a UI component via 21st.dev magic. "
        "[21ST: search_ui|query] searches 21st.dev for component ideas. "
        "[21ST: logos|company1,company2|SVG] gets company logos. "
        "[21ST: refine|message|file|context] improves an existing UI component. "
        "[21ST: install_mcp|cursor] installs 21st MCP config into your IDE. "
        "--- OBSIDIAN NOTES --- "
        "[OBSIDIAN: sync] re-indexes all vault notes into knowledge base + memory. "
        "[OBSIDIAN: log] shows recent sync history. "
        "[OBSIDIAN: stats] shows sync status. "
        "[OBSIDIAN: start] starts background file watcher for auto-sync. "
        "Obsidian notes are synced automatically in the background."
    )})

    def call_llm(msgs):
        import traceback
        for name, fn in [("Groq", call_groq), ("OpenRouter", call_openrouter),
                          ("Gemini", call_gemini), ("HuggingFace", call_huggingface)]:
            try:
                result = fn(msgs)
                if result:
                    return result
            except Exception as e:
                print(f"[LLM] {name} failed: {e}", flush=True)
        raise Exception("All providers failed")

    final_reply = None
    for _ in range(3):
        try:
            reply = call_llm(messages)
        except Exception as e:
            print(f"[LLM] All providers failed: {e}", flush=True)
            break
        if not reply:
            break
        tool_cmd = re.search(r'\[(?:TOOL:\s*)?(WEATHER|NEWS|SEARCH|SCAN|TENDERS|JOBS|GNEWS|RAPIDJOBS|REED|ZIPRECRUITER|WTTJ|DWP|JOBHIVE|OBSIDIAN|KNOWLEDGE|KNOW_INDEX|KB|KB_INDEX|KB_STATS|MEMORY|MEM_Q|MEM_SAVE|MEM_STATS|GSTACK_REVIEW|GSTACK_SPEC|GSTACK_HEALTH|GSTACK_TOOLS|GSTACK_QA|21ST|UI|21ST_DEV)[:\s]\s*(.*?)\]', reply, re.IGNORECASE)
        if tool_cmd:
            full = tool_cmd.group(0)
            print(f"🔧 Tool: {full}", flush=True)
            result = handle_tool(full)
            messages.append({'role': 'assistant', 'content': reply})
            messages.append({'role': 'user', 'content': f"Tool result: {result}\nNow answer."})
        else:
            final_reply = reply
            break
    add_message(session_id, 'gateway', 'user', user_msg)
    add_message(session_id, 'gateway', 'assistant', final_reply)
    return jsonify({"choices": [{"message": {"role": "assistant", "content": final_reply}}]})

if __name__ == '__main__':
    import threading
    def warmup():
        import time
        time.sleep(3)
        try:
            kb._get_model()
            print("[warmup] KB model loaded")
        except Exception as e:
            print(f"[warmup] KB error: {e}")
    threading.Thread(target=warmup, daemon=True).start()
    app.run(host='0.0.0.0', port=8080)
