import requests
import pandas as pd
import os
import pickle
from io import StringIO, BytesIO
from functools import lru_cache

MANIFEST_URL = "https://storage.stapply.ai/jobhive/v1/manifest.json"
CACHE_DIR = "/tmp/jobhive_cache"

_DF_CACHE = {}

@lru_cache(maxsize=1)
def _get_manifest():
    r = requests.get(MANIFEST_URL, timeout=60)
    r.raise_for_status()
    return r.json()

def list_ats_sources():
    return list(_get_manifest().get("by_ats", {}).keys())

def _download_and_cache(ats, url):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{ats}.pkl")
    if os.path.exists(cache_path) and os.path.getmtime(cache_path) > 0:
        try:
            with open(cache_path, "rb") as f:
                df = pickle.load(f)
                _DF_CACHE[ats] = df
                return df
        except Exception:
            pass
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except requests.Timeout:
        raise TimeoutError(
            f"Download timed out for '{ats}'. "
            f"Use a smaller ATS source (try: greenhouse, lever, ashby, breezy, bamboohr, icims, workable) "
            f"or pre-download with: python3 -c \"from scrapers.jobhive_adapter import search_jobhive; print(search_jobhive(query='python', ats='{ats}'))\""
        )
    if url.endswith(".parquet"):
        df = pd.read_parquet(BytesIO(r.content))
    else:
        df = pd.read_csv(StringIO(r.text))
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(df, f)
    except Exception:
        pass
    _DF_CACHE[ats] = df
    return df

def _get_data(ats=None):
    manifest = _get_manifest()
    if ats:
        if ats == "all":
            url = manifest.get("all", {}).get("parquet") or manifest.get("all", {}).get("csv")
            if not url:
                return pd.DataFrame()
            return _download_and_cache("all", url)
        ad = manifest.get("by_ats", {}).get(ats)
        if not ad:
            raise ValueError(f"Unknown ATS '{ats}'")
        url = ad.get("csv") or ad.get("parquet")
        if not url:
            return pd.DataFrame()
        return _download_and_cache(ats, url)
    url = manifest.get("all", {}).get("parquet") or manifest.get("all", {}).get("csv")
    if url:
        return _download_and_cache("all", url)

def search_jobhive(query=None, location=None, company=None, ats=None, remote=False, limit=10):
    try:
        df = _get_data(ats)
    except Exception as e:
        return f"jobhive error: {e}"

    if df is None or df.empty:
        return "No job data available."

    if query:
        df = df[df["title"].fillna("").str.contains(query, case=False, na=False)]
    if location:
        df = df[df["location"].fillna("").str.contains(location, case=False, na=False)]
    if company:
        df = df[df["company"].fillna("").str.contains(company, case=False, na=False)]
    if remote and "location" in df.columns:
        df = df[df["location"].fillna("").str.contains("remote", case=False, na=False)]

    if df.empty:
        return "No jobs found."

    source_label = ats or "all"
    df = df.head(limit)
    output = f"jobhive ({source_label}): {len(df)} jobs\n"
    for _, job in df.iterrows():
        title = job.get("title", "N/A")
        co = job.get("company", "N/A")
        loc = job.get("location", "")
        output += f"- {title} @ {co} ({loc})\n"
    return output
