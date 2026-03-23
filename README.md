# PhDRank — Global PhD Program Placement Rankings

An open, data-driven ranking of PhD programs by **where their graduates actually end up**.

Built on [ORCID](https://orcid.org/) public data (CC-BY 4.0) via the [Zenodo dataset](https://doi.org/10.5281/zenodo.17983291) by Yifeng Li.

**Live site**: [https://soray42.github.io/PhDRank/](https://soray42.github.io/PhDRank/)

## What makes this different

| Feature | PhDRank | CSRankings | QS/THE | US News |
|---------|---------|------------|--------|---------|
| Data source | ORCID (public, verifiable) | DBLP (CS only) | Surveys + reputation | Surveys |
| Scope | Global, multi-field | US CS only | Global | US only |
| Metric | Actual placement outcomes | Faculty pub count | Reputation score | Reputation score |
| Career paths | Academic + Industry + Policy | Academic only | N/A | N/A |
| Reproducible | Fully open source | Partially | No | No |

## Methodology (v1.2)

Each PhD program is scored on 4 dimensions:

- **D (Destination Prestige, 40%)** — OpenAlex `cited_by_count` percentile of each graduate's destination institution, with a 30% international premium.
- **T (Career Tier, 35%)** — LLM-classified role tier (tenure-track 1.0, permanent research 0.85, senior industry 0.80, postdoc 0.50, etc.), weighted by destination prestige. Employer concentration capped at 10%.
- **R (Return Penalty, 10%)** — Self-hire discount. Programs that predominantly employ their own graduates are penalized.
- **I (Quality Index, 15%)** — Dual-regime: top-10% prestigious programs are scored on retention rate; others on value-added uplift.

Key design choices:
- **Inverted PhD filter**: exclude bachelor/master/intern edges, keep everything else
- **10-year window**: graduates from 2016-2025
- **Further education excluded**: edges to another degree program are not placements
- **Global employer prestige**: OpenAlex cited_by_count as universal signal
- **Bayesian shrinkage**: Small programs regress toward field mean (k=20, min N=15)
- **LLM-classified tiers**: 14,239 unique role strings classified, 0.1% unknown

## Fields covered

- Computer Science (247 programs)
- Economics (97 programs)
- Mathematics (90 programs)

**Total: 434 ranked programs across 3 fields.**

More fields planned: Statistics, Physics, Finance, Biology.

## Data pipeline

```
ORCID Public Data (Zenodo, 11M edges)
    |
    +-- extract_v3.sql --> PhD-only field edges (phd3_cs/econ/math.parquet)
    |
    +-- OpenAlex S3 snapshot --> openalex_institutions.csv (120k institutions)
    |
    +-- unique_roles_v3_classified.csv (LLM-classified tiers)
    |
    +-- composite_v12.py --> ranking_v12.json --> docs/data.json (static site)
```

## Local development

```bash
# 1. Download ORCID data from Zenodo
#    DOI: 10.5281/zenodo.17983291 (16.5GB 7z)

# 2. Extract PhD edges (DuckDB)
duckdb < extract_v3.sql

# 3. Compute rankings
pip install pandas numpy pyarrow scipy
python composite_v12.py

# 4. Serve locally
cd docs && python -m http.server 8000
```

## Roadmap

- [x] v0.8: Global employer prestige + career tier + return penalty + dual-regime quality
- [x] v0.9: LLM-classified tiers, 10yr window, inverted PhD filter
- [x] v1.0: International premium + NULL imputation + LLM tiers
- [x] v1.2: OpenAlex cited_by_count as D score
- [ ] v1.3: ROR name resolution (match rate 47% -> 80%+)
- [ ] v1.4: XOR model (Iacovissi & De Bacco 2022) + placement variance penalty
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
- Methodology: Open (see docs/methodology.md)
