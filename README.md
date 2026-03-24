# PhDRank — Global PhD Program Placement Rankings

An open, data-driven ranking of PhD programs by **where their graduates actually end up**.

**Live site**: [https://soray42.github.io/PhDRank/](https://soray42.github.io/PhDRank/)

## What makes this different

| Feature | PhDRank | CSRankings | QS/THE | US News |
|---------|---------|------------|--------|---------|
| Data source | ORCID + CSRankings + econphdplacements.com | DBLP (CS only) | Surveys + reputation | Surveys |
| Scope | Global, multi-field | US CS only | Global | US only |
| Metric | Actual placement outcomes | Faculty pub count | Reputation score | Reputation score |
| Career paths | Academic + Industry + Policy | Academic only | N/A | N/A |
| Reproducible | Fully open source | Partially | No | No |

## Current Rankings (v1.3)

**Computer Science** (368 programs)
| # | Program | N |
|---|---------|---|
| 1 | Carnegie Mellon University | 176 |
| 2 | UC Berkeley | 143 |
| 3 | Stanford University | 111 |
| 4 | MIT | 163 |
| 5 | Tsinghua University | 86 |

**Economics** (192 programs)
| # | Program | N |
|---|---------|---|
| 1 | Harvard University | 323 |
| 2 | MIT | 130 |
| 3 | Princeton University | 231 |
| 4 | Northwestern University | 237 |
| 5 | Stanford University | 235 |

**Mathematics** (195 programs)
| # | Program | N |
|---|---------|---|
| 1 | University of Cambridge | 135 |
| 2 | Peking University | 73 |
| 3 | University of Chicago | 64 |
| 4 | University of Wisconsin-Madison | 73 |
| 5 | UC Berkeley | 82 |

**755 ranked programs, 28K+ graduates, 51 countries.**

## Methodology (v1.3)

Each PhD program is scored on 5 dimensions:

- **D (Destination Prestige, 40%)** — SpringRank-based prestige using `log(indegree) × cross-community source quality` from the global PhD placement network (200k edges, 58k institutions). Includes 1,174 company prestige overrides for industry destinations. International placements get a 30% premium.
- **T (Career Tier, 35%)** — LLM-classified role tier (tenure-track 1.0, permanent research 0.85, senior industry 0.80, postdoc 0.50, etc.), weighted by destination prestige. Employer concentration capped at 10%.
- **R (Return Penalty, 10%)** — Self-hire discount, with exemption for prestigious schools (top-20% by SpringRank). MIT hiring its own graduates is a prestige signal, not nepotism.
- **I (Quality Index, 15%)** — Retention rate: percentage of graduates going to destinations with prestige above the 60th percentile.
- **V (Variety Bonus, 5%)** — Rewards programs with diverse outcomes (destination entropy + career tier diversity). Penalizes monotone placements.

Key design choices:
- **SpringRank** on global placement flow network for size-independent prestige
- **Louvain community detection** (915 clusters) to identify geographic/cultural hiring patterns
- **Community-adjusted D score**: cross-community source quality weighted 70% to discount insular hiring
- **Tier × Region edge quality**: edges crossing both prestige tier and community get 1.10x multiplier
- **Inverted PhD filter**: exclude bachelor/master/intern edges, keep everything else
- **10-year window**: graduates from 2016-2025
- **Bayesian shrinkage**: k=40, min N=15
- **Accent normalization**: merges university name variants across languages (ETH Zurich/ETH Zürich, Bocconi/Università Bocconi)

## Data sources

1. **ORCID Public Data** — [Zenodo DOI:10.5281/zenodo.17983291](https://doi.org/10.5281/zenodo.17983291) (11M education→employment edges, CC-BY 4.0)
2. **CSRankings** — [github.com/emeryberger/CSrankings](https://github.com/emeryberger/CSrankings) (33k CS faculty, cross-referenced with ORCID for PhD school)
3. **econphdplacements.com** — 9,165 econ PhD placement records from 44 top programs (2016-2025)

## Data pipeline

```
ORCID Public Data (Zenodo, 11M edges)
    |
    +-- DuckDB extraction --> phd4_cs/econ/math.parquet
    |     (expanded keywords: +eecs, +statistics, +public policy)
    |     (NULL dept recovery: infer field from destination dept)
    |
    +-- CSRankings × ORCID cross-reference --> +2,521 CS faculty edges
    +-- econphdplacements.com --> +5,667 econ placement edges
    |
    +-- global_emp_inflow.parquet (200k edges)
    |     --> SpringRank (57k nodes) --> springrank_scores.json
    |     --> Louvain communities (915 clusters) --> node_communities.json
    |     --> dest_prestige_sr.json (50k+ entries)
    |     --> + 1,174 company prestige overrides
    |
    +-- unique_roles_v3_classified.csv (14k LLM-classified tiers)
    |
    +-- composite_v13.py --> ranking_v13.json --> docs/data.json
```

## Local development

```bash
# 1. Download ORCID data from Zenodo
#    DOI: 10.5281/zenodo.17983291 (16.5GB 7z)

# 2. Extract PhD edges (DuckDB)
duckdb < extract_v3.sql

# 3. Compute SpringRank + community prestige
pip install pandas numpy pyarrow scipy springrank networkx
python compute_community_prestige.py

# 4. Compute rankings
python scripts/composite_v13.py --data-dir . --output-dir .

# 5. Serve locally
cd docs && python -m http.server 8000
```

## Roadmap

- [x] v0.8: Global employer prestige + career tier + return penalty
- [x] v0.9: LLM-classified tiers, 10yr window, inverted PhD filter
- [x] v1.0: International premium + NULL imputation
- [x] v1.2: OpenAlex cited_by_count as D score
- [x] v1.3: SpringRank prestige, community adjustment, external data (CSRankings + econphdplacements), 1,174 company overrides, school dedup, variety bonus
- [ ] v1.4: More fields (Physics, Statistics, Biology)
- [ ] v1.5: OpenAlex author affiliations for broader coverage
- [ ] v2.0: Temporal trends, head-to-head comparisons, per-graduate ORCID links

## Citation

If you use this data or methodology, please cite:

```
@misc{phdrank2026,
  title={PhDRank: Global PhD Program Placement Rankings},
  author={Sora},
  year={2026},
  url={https://github.com/soray42/PhDRank}
}
```

## License

- Code: MIT
- Data: CC-BY 4.0 (derived from ORCID public data)
- Methodology: Open
