#!/usr/bin/env python3
"""
OpenAlex institution prestige v2 — uses search API + filters for better matching.
Run locally: python openalex_prestige_v2.py
"""
import requests, time, csv, json

EMAIL = "soray42@proton.me"
BASE = "https://api.openalex.org"
SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': f'PhDRank/0.1 (mailto:{EMAIL})',
    'Accept': 'application/json',
})

# For companies, search with display_name.search filter and pick the one
# with highest works_count (= the main entity, not a subsidiary)
TARGETS = [
    # (query, expected_type or None)
    # Tech
    ("Google", "company"), ("Microsoft", "company"), ("Meta", "company"),
    ("Apple", "company"), ("Amazon", "company"), ("NVIDIA", "company"),
    ("IBM", "company"), ("DeepMind", None), ("OpenAI", "company"),
    ("Anthropic", "company"), ("ByteDance", "company"), ("Tencent", "company"),
    ("Alibaba", "company"), ("Samsung", "company"), ("Intel", "company"),
    ("Huawei", "company"), ("Baidu", "company"), ("Adobe", "company"),
    ("Salesforce", "company"), ("Oracle", "company"), ("Uber", "company"),
    # Quant/Finance
    ("Jane Street", "company"), ("Citadel", "company"), ("Two Sigma", "company"),
    ("D. E. Shaw Research", None), ("Renaissance Technologies", "company"),
    ("Bridgewater", "company"), ("Goldman Sachs", "company"),
    ("JPMorgan", "company"), ("Morgan Stanley", "company"), ("BlackRock", "company"),
    # Consulting
    ("McKinsey", "company"), ("Boston Consulting Group", "company"),
    ("Bain & Company", "company"),
    # National labs
    ("Los Alamos National Laboratory", None), ("Sandia National Laboratories", None),
    ("Lawrence Berkeley National Laboratory", None), ("Argonne National Laboratory", None),
    ("Oak Ridge National Laboratory", None), ("Brookhaven National Laboratory", None),
    ("CERN", None), ("NASA", None),
    # Pharma
    ("Pfizer", "company"), ("Novartis", "company"), ("Roche", "company"),
    ("Merck", "company"), ("AstraZeneca", "company"), ("Genentech", "company"),
    ("Moderna", "company"),
    # Policy
    ("World Bank", None), ("International Monetary Fund", None),
    ("Federal Reserve", None), ("RAND Corporation", None),
    # Universities for calibration
    ("Massachusetts Institute of Technology", "education"),
    ("Stanford University", "education"), ("Harvard University", "education"),
    ("Princeton University", "education"), ("University of Cambridge", "education"),
    ("Carnegie Mellon University", "education"),
    ("University of California, Berkeley", "education"),
    ("University of Tokyo", "education"), ("Peking University", "education"),
    ("ETH Zurich", "education"),
]

def search_institution(query, expected_type=None):
    """Use the institutions search endpoint for better matching."""
    # Try search endpoint first
    url = f"{BASE}/institutions?search={query}&mailto={EMAIL}&per_page=5"
    if expected_type:
        url += f"&filter=type:{expected_type}"
    
    r = SESSION.get(url, timeout=15)
    if r.status_code != 200:
        return {'query': query, 'error': f'HTTP {r.status_code}: {r.text[:100]}'}
    
    try:
        data = r.json()
    except:
        return {'query': query, 'error': f'JSON fail: {r.text[:100]}'}
    
    results = data.get('results', [])
    if not results:
        # Retry without type filter
        if expected_type:
            url2 = f"{BASE}/institutions?search={query}&mailto={EMAIL}&per_page=5"
            r2 = SESSION.get(url2, timeout=15)
            try:
                data2 = r2.json()
                results = data2.get('results', [])
            except:
                pass
    
    if not results:
        return {'query': query, 'error': 'no results'}
    
    # Pick the result with highest works_count (= main entity)
    best = max(results, key=lambda x: x.get('works_count', 0))
    
    return {
        'query': query,
        'openalex_id': best.get('id', '').split('/')[-1],
        'display_name': best.get('display_name', ''),
        'type': best.get('type', ''),
        'country_code': best.get('country_code', ''),
        'works_count': best.get('works_count', 0),
        'cited_by_count': best.get('cited_by_count', 0),
        'ror': best.get('ror', ''),
        'homepage': best.get('homepage_url', ''),
    }

def main():
    results = []
    errors = []
    
    print(f"Querying {len(TARGETS)} institutions...")
    print(f"{'Query':<40s} {'Matched Name':<45s} {'Type':<10s} {'Works':>10s} {'Cited':>12s}")
    print("-" * 125)
    
    for query, etype in TARGETS:
        data = search_institution(query, etype)
        
        if 'error' in data:
            print(f"{query:<40s} ERROR: {data['error']}")
            errors.append(data)
        else:
            results.append(data)
            dn = data['display_name'][:44]
            tp = data.get('type','?')
            wc = data['works_count']
            cc = data['cited_by_count']
            print(f"{query:<40s} {dn:<45s} {tp:<10s} {wc:>10,d} {cc:>12,d}")
        
        time.sleep(0.3)
    
    # Save
    fields = ['query','openalex_id','display_name','type','country_code',
              'works_count','cited_by_count','ror','homepage']
    with open('openalex_prestige_v2.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(results)
    
    print(f"\nSaved openalex_prestige_v2.csv ({len(results)} found, {len(errors)} errors)")
    
    # Summary: which companies have enough data to be useful?
    print("\n=== USABILITY ASSESSMENT ===")
    for data in sorted(results, key=lambda x: -x['cited_by_count']):
        wc = data['works_count']
        if data.get('type') in ('education', 'facility', 'government'):
            continue
        label = "GOOD" if wc > 500 else "USABLE" if wc > 50 else "SPARSE" if wc > 0 else "NONE"
        print(f"  [{label:6s}] {data['query']:<35s} works={wc:>8,d}  cited={data['cited_by_count']:>12,d}")

if __name__ == '__main__':
    main()
