#!/usr/bin/env python3
import sys, os
sys.path.append(os.path.dirname(__file__))

from scrapers import search_jobhive, search_jooble, search_dwp_uk, search_adzuna

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_scraper.py <source> [keyword] [loc=...]")
        print("Sources: jobhive, jooble, dwp, adzuna, list-ats")
        return

    cmd = sys.argv[1]
    if cmd == "list-ats":
        from scrapers.jobhive_adapter import list_ats_sources
        ats_list = list_ats_sources()
        print(f"Available ATS platforms ({len(ats_list)}):")
        for a in sorted(ats_list):
            print(f"  - {a}")
        return

    keyword = ""
    location = None
    ats = None
    for a in sys.argv[2:]:
        if a.startswith("loc="):
            location = a.split("=", 1)[1]
        elif a.startswith("ats="):
            ats = a.split("=", 1)[1]
        elif not a.startswith("="):
            keyword = a

    if cmd == "jobhive":
        print(search_jobhive(query=keyword, location=location, ats=ats, limit=10))
    elif cmd == "jooble":
        print(search_jooble(keyword=keyword, location=location, limit=10))
    elif cmd == "dwp":
        print(search_dwp_uk(query=keyword if keyword else "data engineer", limit=10))
    elif cmd == "adzuna":
        print(search_adzuna(keyword if keyword else "developer"))
    else:
        print(f"Unknown source: {cmd}")

if __name__ == "__main__":
    main()
