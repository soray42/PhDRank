# PhDRank Composite Scoring Formula
## Version 0.2 — Full specification

---

## Overview

The composite score for each PhD program is:

    S(p) = α·D(p) + β·T(p) + γ·M(p) + δ·R(p) + ε·I(p) + ζ·P(p)

where:
- D = Destination prestige score
- T = Career tier score
- M = Mobility score (geographic + institutional)
- R = Return penalty adjustment
- I = Input quality control
- P = Publication productivity (Phase 2)
- α,β,γ,δ,ε,ζ = weights calibrated from data

All sub-scores are normalized to [0, 1] before weighting.
The final composite S(p) is also normalized to [0, 100].

---

## Sub-score 1: Destination prestige — D(p)

### Definition
For each graduate g of program p, compute the prestige of their
destination institution using global log-indegree:

    prestige(dest) = log(1 + indegree(dest)) / max_log_indegree

where indegree(dest) = number of unique people flowing into dest
across the entire ORCID dataset (not field-specific — a globally
attractive institution is prestigious regardless of field).

    D(p) = (1/N_p) · Σ_g prestige(dest_g)

with Bayesian shrinkage: D̃(p) = (N_p·D(p) + k·μ_D) / (N_p + k)
where k = 30, μ_D = global mean.

### Justification
- Equivalent to Amir & Knauff (2008) concept: value of program =
  sum of values of destinations
- Log transform prevents outliers (MIT with 10000 indegree vs
  small college with 5) from dominating
- Global indegree avoids the circular dependency problem of
  field-specific SpringRank (where small samples cause noise)

---

## Sub-score 2: Career tier — T(p)

### Definition
Classify each graduate's role_to into tiers using keyword matching:

| Tier | Score | Detection keywords |
|------|-------|--------------------|
| T1: Tenure-track faculty | 1.00 | "professor", "assistant prof", "associate prof", "full prof", "教授", "助教", "准教授", "講師" (at university org) |
| T2: Permanent research | 0.85 | "researcher", "scientist", "research fellow", "研究員" (at research institute, with no "postdoc"/"visiting") |
| T3: Industry senior | 0.80 | "senior engineer", "senior scientist", "director", "manager", "VP", "lead", "principal" |
| T4: Industry entry | 0.65 | "engineer", "developer", "analyst", "data scientist", "consultant" |
| T5: Government/policy | 0.75 | Employer contains "ministry", "government", "federal", "IMF", "world bank", "central bank", "OECD" |
| T6: Postdoc/temporary | 0.50 | "postdoc", "post-doc", "visiting", "research associate", "fellow" (temporary) |
| T7: Further education | 0.30 | role_type_to = 'education' AND role_to contains "phd", "master", "student" |
| T8: Unknown/other | 0.50 | role_to is NULL, empty, or unclassifiable |

    T(p) = (1/N_p) · Σ_g tier_score(g)

### Tier score justification
- T1 (1.0) = gold standard outcome, anchors the scale
- T6 (0.5) = postdoc is a legitimate but temporary step; it's not
  a terminal outcome and may lead to T1 later — discount by 50%
- T3-T4 (0.65-0.80) = industry is a valid career; senior roles
  reflect program quality more than junior roles
- T7 (0.3) = further education means the PhD didn't lead to a
  career outcome yet — low but not zero (could be a prestigious
  second degree)
- T8 (0.5) = unknown gets the median score (principle of maximum
  entropy — don't reward or penalize what we can't observe)

### Sensitivity analysis
The tier scores above are INITIAL values. We test robustness by:
1. Running ranking with T6 ∈ {0.3, 0.4, 0.5, 0.6, 0.7}
2. Running with T3-T4 ∈ {0.5, 0.65, 0.80, 0.90}
3. Report Kendall τ between rankings across all settings
4. If τ > 0.90 for all pairs → tier scores don't matter much
   → report "robust to tier definition"

---

## Sub-score 3: Mobility — M(p)

### Definition
Measures geographic and institutional diversity of outcomes.

    M(p) = 0.6 · international_rate(p) + 0.4 · institutional_diversity(p)

where:
- international_rate(p) = fraction of graduates whose dest_country ≠ phd_country
- institutional_diversity(p) = normalized entropy of destination distribution:
  H(p) / log(N_p), where H(p) = -Σ_d (n_d/N_p)·log(n_d/N_p)

### Why this matters
- A program that sends 80% of graduates to the same 2 institutions
  (even if prestigious) is less valuable than one that places across
  20 diverse institutions
- International mobility signals broader recognition of the degree
- Entropy is a principled measure of diversity (information theory)

### Geographic bias handling
NOT a penalty for staying in one's own country. Rather, a BONUS
for demonstrated international portability. A US school where 90%
stay in the US but go to 50 different institutions still gets high
institutional_diversity — it's the concentration that's penalized,
not the geography per se.

---

## Sub-score 4: Return adjustment — R(p)

### Definition
Penalizes two specific patterns that indicate weak placement:

    R(p) = 1 - λ₁·self_return_rate(p) - λ₂·hometown_bias(p)

where:
- self_return_rate = fraction of graduates whose dest = phd_school
  (same institution). λ₁ = 0.5 (strong penalty — this usually
  indicates RA/TA during PhD, not genuine placement)
- hometown_bias = fraction of graduates returning to their pre-PhD
  institution (requires Query 8 data). λ₂ = 0.3 (moderate penalty —
  returning to your undergrad institution after PhD elsewhere is
  a weaker signal than going to a new institution)

Note: returning to one's home COUNTRY is NOT penalized here.
That's handled separately in the mobility score M(p).

### Why self-return is penalized
Data shows schools like Sumy State (80.3%), Ben-Gurion (75.2%),
Riga Tech (74.3%) have extreme self-hire rates. This inflates their
placement statistics — they appear to "place" many people but are
actually just retaining their own students as employees. A genuine
placement metric must discount this.

### Calibration
λ₁ = 0.5 means: if 100% of graduates stay at the same school,
R(p) = 0.5 (halved score). If 0% stay, R(p) = 1.0 (no penalty).
The median self-return rate is ~30%, so R(p) ≈ 0.85 for a typical school.

---

## Sub-score 5: Input quality control — I(p)

### Definition
Controls for the quality of incoming students. A program that
admits students from Harvard/Tsinghua and places them at Stanford
is less impressive than one that admits from regional universities
and still places at Stanford.

    I(p) = max(0, placement_uplift(p))

    placement_uplift(p) = D(p) - weighted_mean(prestige(origin_g))

where origin_g is the pre-PhD institution of graduate g (from
education → education edges in aff.parquet).

If placement_uplift > 0: the program adds value (graduates go to
better places than where they came from). Score = uplift, capped at 1.

If placement_uplift ≤ 0: the program doesn't add value relative to
input. Score = 0 (floor, not negative — we don't punish, just don't
reward).

### Data availability
Query 4 shows 935K people have ≥2 education edges, 528K have ≥3.
Query 8 shows clear feeder patterns (Tsinghua→Princeton, Tehran→Purdue).
This is feasible for ~60% of graduates. For the ~40% with only 1
education edge (no known pre-PhD origin), we impute I = 0.5 (neutral).

### Why this matters
Without input control, the ranking simply reflects which programs
attract the best students — not which programs add the most value.
This is the VALUE-ADDED dimension that no existing ranking captures.

---

## Sub-score 6: Publication productivity — P(p) [Phase 2]

### Definition
For each graduate with an ORCID, query OpenAlex for publications
within 5 years post-PhD:

    pub_score(g) = w₁·n_top_journal + w₂·log(1 + n_total_pubs)

where:
- n_top_journal = count of publications in field-specific top journals
  (CS: ICML/NeurIPS/CVPR/SIGMOD/etc; Econ: Top 5 + JFE/RFS/REStat;
  Math: Annals/Inventiones/Acta/JAMS/Duke)
- n_total_pubs = total publications in any venue
- w₁ = 0.7, w₂ = 0.3 (quality > quantity)

    P(p) = (1/N_p) · Σ_g pub_score(g) / max_pub_score

### Data source
OpenAlex API, joined via ORCID ID (available for all graduates).
Phase 2 implementation — not in initial launch.

---

## Weight calibration procedure

### Step 1: Expert prior (Delphi-like)
Set initial weights based on revealed preference in existing literature:

| Weight | Component | Initial | Rationale |
|--------|-----------|---------|-----------|
| α | Destination prestige | 0.30 | Core metric (Amir-Knauff, Wapman) |
| β | Career tier | 0.25 | Key distinction (econphdplacements) |
| γ | Mobility | 0.10 | Informative but secondary |
| δ | Return adjustment | 0.10 | Correction factor |
| ε | Input quality control | 0.15 | Value-added is novel, important |
| ζ | Publication (Phase 2) | 0.10 | Post-PhD productivity |

Phase 1 (no publications): redistribute ζ proportionally →
α=0.333, β=0.278, γ=0.111, δ=0.111, ε=0.167

### Step 2: Cross-validation calibration
Use existing rankings as ground truth for calibration:

For CS: CSRankings (publication-based), Wapman prestige ranks
For Econ: Tilburg ranking, Amir-Knauff (2008) ranking, RePEc
For Math: Shanghai ARWU subject ranking

Procedure:
1. Compute S(p) with initial weights
2. Compute Spearman ρ between S(p) and each external ranking
3. Optimize weights to maximize average ρ across external rankings
4. Constraint: all weights ∈ [0.05, 0.50], sum = 1.0
5. Use scipy.optimize.minimize with Nelder-Mead

This is NOT fitting to the external rankings — it's using them as
anchors to find weights that produce reasonable orderings. The
optimization can only move weights within bounds, and the result
must still pass the sensitivity analysis below.

### Step 3: Sensitivity analysis
For each weight, vary it ±50% while adjusting others proportionally.
Report:
- Kendall τ of top-50 ranking vs baseline for each perturbation
- Maximum rank change for any school in top-50
- Set of "stable schools" (rank changes < 5 in all perturbations)

If the ranking is sensitive to a particular weight (τ < 0.85),
that component needs more careful justification or should be
downweighted.

### Step 4: Bootstrap uncertainty
For each school:
1. Resample graduates with replacement, 1000 times
2. Compute S(p) each time
3. Report 95% CI on rank
4. If CI spans > 30 positions, flag as "rank uncertain"

---

## Implementation note: 5-year rolling window

Data is filtered to graduates whose phd_end_year falls within
the most recent 5-year window: [current_year - 5, current_year].

Updated every 6 months when ORCID releases new data dumps.
Each release gets a version stamp (e.g., "2026H1", "2026H2").

Historical rankings are archived for trend analysis.

---

## Implementation note: field keyword expansion

Phase 1 fields and their department keywords:

**Computer Science**: computer, informatic, computing, artificial
intelligence, machine learning, data science, software engineer,
情報, 計算, cybersecurity, information system

**Economics**: econom, 経済, political economy, public policy,
development studies, agricultural economics

**Mathematics**: mathematic, 数学, applied math, pure math,
mathematical sciences

**Finance** (Phase 2): financ, 金融, accounting, 会計, actuarial

**Statistics** (Phase 2): statistic, 統計, biostatistic, econometric,
data analytics

**Physics** (Phase 2): physic, 物理, astrophysic, theoretical physics

---

## Summary: what makes this ranking different

1. **Composite, not single-metric**: 5 dimensions (6 with publications)
   vs Wapman's 1 (SpringRank) or Tilburg's 1 (pub count)

2. **Data-driven weights**: calibrated against external rankings +
   sensitivity analysis, not editorially chosen

3. **Value-added**: input quality control is a novel dimension that
   captures whether a program improves its students, not just whether
   it admits good ones

4. **Career-path agnostic**: industry, government, academia all count,
   with tier scores reflecting career quality not career path

5. **Global**: not US-only (Wapman) or survey-based (QS/THE)

6. **Reproducible**: built entirely on CC-BY ORCID data, open-source
   code, documented methodology

7. **Rolling updates**: 5-year window, semi-annual refresh
