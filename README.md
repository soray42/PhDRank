# PhDRank — Global PhD Program Placement Rankings

An open, data-driven ranking of PhD programs by **where their graduates actually end up**.

Built on [ORCID](https://orcid.org/) public data (CC-BY 4.0) via the [Zenodo dataset](https://doi.org/10.5281/zenodo.17983291) by Yifeng Li.

**Live site**: [https://phdrank.github.io](https://phdrank.github.io)

## What makes this different

| Feature | PhDRank | CSRankings | QS/THE | US News |
|---------|---------|------------|--------|---------|
| Data source | ORCID (public, verifiable) | DBLP (CS only) | Surveys + reputation | Surveys |
| Scope | Global, multi-field | US CS only | Global | US only |
| Metric | Actual placement outcomes | Faculty pub count | Reputation score | Reputation score |
| Career paths | Academic + Industry + Policy | Academic only | N/A | N/A |
| Reproducible | Fully open source | Partially | No | No |

## Methodology (v0.8)

Each PhD program is scored on 4 dimensions:

- **D (Destination Prestige, 40%)** — Where do graduates go? Measured by global employer prestige derived from 820k education→employment transitions across all fields.
- **T (Career Tier, 35%)** — What do graduates do? Tenure-track faculty (1.0), permanent researcher (0.85), senior industry (0.80), postdoc (0.50), etc.
- **R (Return Penalty, 10%)** — Self-hire discount. Programs that predominantly employ their own graduates are penalized.
- **I (Quality Index, 15%)** — Dual-regime: for prestigious programs, measures retention rate (% of graduates landing at equally prestigious destinations); for others, measures value-added uplift.

Key design choices:
- **PhD-only edges**: Only doctoral-level graduates, filtered by `role_from` keyword matching
- **Global employer prestige**: log(inflow) × avg(source quality) across 820k people, 52k employers
- **Bayesian shrinkage**: Small programs regress toward field mean (k=20)
- **Dual-regime I score**: Top-20% programs assessed on retention, others on uplift

## Fields covered

- Computer Science (498 programs)
- Economics (321 programs)
- Mathematics (291 programs)

More fields coming: Statistics, Physics, Finance, Biology.

## Data pipeline

```
ORCID Public Data (Zenodo, 11M edges)
    │
    ├─ extract_phd.sql ──→ PhD-only field edges (phd_cs/econ/math.parquet)
    ├─ extract_inflow.sql → Global employment inflow (global_emp_inflow.parquet)
    │
    └─ composite_v08.py ─→ ranking_v08.json ─→ index.html (static site)
```

## Local development

```bash
# 1. Download ORCID data from Zenodo
#    DOI: 10.5281/zenodo.17983291 (16.5GB 7z)

# 2. Extract PhD edges
duckdb < scripts/extract_phd.sql

# 3. Extract global inflow network
duckdb < scripts/extract_inflow.sql

# 4. Compute rankings
pip install pandas numpy pyarrow scipy springrank
python scripts/composite_v08.py

# 5. Serve locally
cd site && python -m http.server 8000
```

## Roadmap

- [x] v0.8: Global employer prestige + career tier + return penalty + dual-regime quality
- [ ] v0.9: OpenAlex integration for industry prestige (cited_by_count as universal signal)
- [ ] v1.0: Professor-level and lab-level placement data
- [ ] v1.1: Temporal trends (5-year rolling windows)
- [ ] v1.2: Interactive filters (by country, career path, destination type)

## Citation

If you use this data or methodology, please cite:

```
@misc{phdrank2026,
  title={PhDRank: Global PhD Program Placement Rankings},
  author={[TBD]},
  year={2026},
  url={https://github.com/phdrank/phdrank}
}
```

## License

- Code: MIT
- Data: CC-BY 4.0 (derived from ORCID public data)
- Methodology: Open (see docs/methodology.md)
