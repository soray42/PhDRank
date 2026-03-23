#!/usr/bin/env python3
"""
PhDRank v1.3 — ROR-enhanced name resolution + OpenAlex cited_by_count

Builds on v1.2 scoring formula:
  Score = D(40%) + T(35%) + R(10%) + I(15%)
  D = OpenAlex cited_by_count percentile × (1 + 0.3 × is_international)
  T = tier_score × (0.5 + 0.5 × dest_prestige), concentration cap 10%
  R = 1 - 0.7 × self_return_rate
  I = dual regime: top-10% → retention, others → uplift percentile

Three-layer name matching:
  L1: ORCID name → OpenAlex display_name (exact normalized)
  L2: ORCID name → OpenAlex alt_names + acronyms (exact normalized)
  L3: ORCID name → ROR names/aliases → ROR ID → OpenAlex (bridge)
  L4: Smart normalization (corporate suffix strip, "at" removal, fuzzy)

Usage:
    python composite_v13.py --data-dir C:\\path\\to\\sodenkai --ror-path ror-data/v2.4-2026-03-12-ror-data.json
"""
import pandas as pd
import numpy as np
import json
import csv
import re
import argparse
import os
import sys
from collections import Counter

# ═══════════════════════════════════════════════════════════
# CONFIGURATION (v1.2 formula)
# ═══════════════════════════════════════════════════════════

MIN_N = 15
SHRINKAGE_K = 20
WEIGHTS = {'D': 0.40, 'T': 0.35, 'R': 0.10, 'I': 0.15}
INTL_ALPHA = 0.3  # international premium
CONC_CAP = 0.10   # employer concentration cap

TIER_SCORES = {
    'tenure_track': 1.0,
    'permanent_research': 0.85,
    'industry_senior': 0.80,
    'government': 0.75,
    'industry_entry': 0.65,
    'postdoc': 0.50,
    'null_academic': 0.70,
    'null_industry': 0.65,
    'unknown': 0.50,
}

# Corporate suffixes to strip
CORP_SUFFIXES = re.compile(
    r'\s*\b(inc\.?|corp\.?|llc|ltd\.?|co\.?\s*ltd\.?|gmbh|ag|sa|plc|'
    r'pvt\.?\s*ltd\.?|pty\.?\s*ltd\.?|s\.?a\.?|s\.?r\.?l\.?|'
    r'b\.?v\.?|n\.?v\.?|ab|oy|as|a/s|kk|k\.?k\.?)\s*$',
    re.IGNORECASE
)

GOV_KW = [
    'ministry', 'government', 'federal', 'national institute',
    'world bank', 'imf ', 'international monetary', 'united nations',
    'oecd', 'central bank', 'reserve bank', 'european commission',
]

# ═══════════════════════════════════════════════════════════
# NAME NORMALIZATION
# ═══════════════════════════════════════════════════════════

def normalize(s):
    """Normalize institution name for matching."""
    s = s.lower().strip()
    s = re.sub(r'^the\s+', '', s)               # remove leading "the"
    s = re.sub(r'\s*\([^)]*\)\s*', ' ', s)      # remove parenthetical
    s = re.sub(r'[,.:;\"\']+', '', s)            # remove punctuation
    s = re.sub(r'[-\u2013\u2014]+', ' ', s)      # normalize dashes
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_aggressive(s):
    """More aggressive normalization for fallback matching."""
    s = normalize(s)
    s = CORP_SUFFIXES.sub('', s).strip()         # strip corporate suffix
    s = re.sub(r'\bat\b', '', s).strip()         # remove "at" (univ of X at Y)
    s = re.sub(r'\bin\b', '', s).strip()         # remove "in" (univ in city)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ═══════════════════════════════════════════════════════════
# NAME MATCHING ENGINE
# ═══════════════════════════════════════════════════════════

def build_matching_engine(openalex_csv, ror_json_path=None):
    """
    Build a comprehensive name → cited_by_count matching engine.
    Returns: dict mapping normalized_name → (cited_by_count, display_name, match_layer)
    """
    print("Building matching engine...")
    oa = pd.read_csv(openalex_csv)
    print(f"  OpenAlex: {len(oa)} institutions")

    # Primary lookup: normalized name → (cited_by_count, display_name)
    lookup = {}       # normal-normalized
    lookup_agg = {}   # aggressive-normalized

    def add(key, cbc, dn, layer, aggressive=False):
        target = lookup_agg if aggressive else lookup
        if key and (key not in target or cbc > target[key][0]):
            target[key] = (cbc, dn, layer)

    # Layer 1: display_name
    for _, row in oa.iterrows():
        cbc = int(row['cited_by_count']) if pd.notna(row['cited_by_count']) else 0
        dn = row['display_name']
        add(normalize(str(row['display_name_lower'])), cbc, dn, 'L1_display')
        add(normalize_aggressive(str(row['display_name_lower'])), cbc, dn, 'L1_display', aggressive=True)

    # Layer 2: alt_names + acronyms
    for _, row in oa.iterrows():
        cbc = int(row['cited_by_count']) if pd.notna(row['cited_by_count']) else 0
        dn = row['display_name']
        if pd.notna(row['alt_names']):
            for a in str(row['alt_names']).split('|'):
                add(normalize(a), cbc, dn, 'L2_alt')
                add(normalize_aggressive(a), cbc, dn, 'L2_alt', aggressive=True)
        if pd.notna(row['acronyms']):
            for a in str(row['acronyms']).split('|'):
                add(normalize(a), cbc, dn, 'L2_acronym')
                add(normalize_aggressive(a), cbc, dn, 'L2_acronym', aggressive=True)

    print(f"  L1+L2 lookup: {len(lookup)} normal, {len(lookup_agg)} aggressive")

    # Layer 3: ROR bridge (ROR name variants → ROR ID → OpenAlex)
    if ror_json_path and os.path.exists(ror_json_path):
        print(f"  Loading ROR from {ror_json_path}...")
        with open(ror_json_path, 'r', encoding='utf-8') as f:
            ror_data = json.load(f)
        print(f"  ROR: {len(ror_data)} records")

        # Build ROR ID → OpenAlex cited_by_count bridge
        oa_by_ror = {}
        for _, row in oa.iterrows():
            if pd.notna(row['ror']):
                oa_by_ror[str(row['ror']).strip()] = (
                    int(row['cited_by_count']) if pd.notna(row['cited_by_count']) else 0,
                    row['display_name']
                )

        ror_added = 0
        for rec in ror_data:
            ror_id = rec['id'].split('/')[-1]
            if ror_id not in oa_by_ror:
                continue
            cbc, dn = oa_by_ror[ror_id]
            names = []
            if 'names' in rec:
                for ne in rec['names']:
                    names.append(ne.get('value', ''))
            for n in names:
                k = normalize(n)
                if k and k not in lookup:
                    lookup[k] = (cbc, dn, 'L3_ror')
                    ror_added += 1
                ka = normalize_aggressive(n)
                if ka and ka not in lookup_agg:
                    lookup_agg[ka] = (cbc, dn, 'L3_ror')

        print(f"  L3 ROR bridge: +{ror_added} new entries")

    # Layer 4: Company parent matching
    # For "google (united states)" etc., also index just "google"
    for _, row in oa.iterrows():
        cbc = int(row['cited_by_count']) if pd.notna(row['cited_by_count']) else 0
        dn = row['display_name']
        name_lower = str(row['display_name_lower'])
        # Match "company (country)" pattern
        m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', name_lower)
        if m:
            base = normalize(m.group(1))
            if base and (base not in lookup_agg or cbc > lookup_agg[base][0]):
                lookup_agg[base] = (cbc, dn, 'L4_parent')

    # Layer 5: Prefix matching
    # "purdue university" → "purdue university west lafayette" (highest cbc)
    # Build sorted list of all OA normalized names for prefix search
    oa_norm_to_cbc = {}  # normalized OA name → (cbc, display_name)
    for _, row in oa.iterrows():
        cbc = int(row['cited_by_count']) if pd.notna(row['cited_by_count']) else 0
        dn = row['display_name']
        k = normalize(str(row['display_name_lower']))
        if k and (k not in oa_norm_to_cbc or cbc > oa_norm_to_cbc[k][0]):
            oa_norm_to_cbc[k] = (cbc, dn)
    # Store for prefix lookups at match time
    _prefix_candidates = oa_norm_to_cbc

    print(f"  Combined lookup: {len(lookup)} normal, {len(lookup_agg)} aggressive")
    print(f"  Prefix candidates: {len(_prefix_candidates)}")
    return lookup, lookup_agg, _prefix_candidates


def match_name(name, lookup, lookup_agg, prefix_candidates=None):
    """Try matching a name through all layers."""
    # Try normal normalization first
    k = normalize(name)
    if k in lookup:
        return lookup[k]

    # Try aggressive normalization
    ka = normalize_aggressive(name)
    if ka in lookup_agg:
        return lookup_agg[ka]

    # Try stripping " research" suffix for companies (e.g., "ibm research" → "ibm")
    ka2 = re.sub(r'\s+research\b.*$', '', ka).strip()
    if ka2 != ka and ka2 in lookup_agg:
        return lookup_agg[ka2]

    # Try removing " web services" etc.
    ka3 = re.sub(r'\s+(web services|labs?|technologies?|platforms?)\b.*$', '', ka).strip()
    if ka3 != ka and ka3 in lookup_agg:
        return lookup_agg[ka3]

    # Layer 5: Prefix matching — "purdue university" matches
    # "purdue university west lafayette" (pick highest cbc)
    if prefix_candidates and len(k) >= 10:
        best = None
        for oa_name, (cbc, dn) in prefix_candidates.items():
            if oa_name.startswith(k + ' ') and cbc > 0:
                if best is None or cbc > best[0]:
                    best = (cbc, dn, 'L5_prefix')
        if best:
            return best

    return None


# ═══════════════════════════════════════════════════════════
# TIER CLASSIFICATION (using LLM-classified tiers if available)
# ═══════════════════════════════════════════════════════════

def load_tier_mapping(csv_path):
    """Load LLM-classified role → tier mapping."""
    mapping = {}
    if not os.path.exists(csv_path):
        return None
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            role = row.get('role_to', '').lower().strip()
            tier = row.get('tier', '').strip()
            if role and tier:
                mapping[role] = tier
    print(f"  LLM tier mapping: {len(mapping)} roles")
    return mapping


def classify_tier_fallback(role_to, dest_type, dest):
    """Rule-based tier classification as fallback."""
    role = str(role_to).lower().strip() if pd.notna(role_to) else ''
    dtype = str(dest_type).lower().strip() if pd.notna(dest_type) else ''
    org = str(dest).lower().strip() if pd.notna(dest) else ''

    if dtype == 'education':
        if any(k in role for k in ['phd', 'doctor', 'master', 'student', 'bachelor']):
            return 'further_education'
        if role == '':
            return 'null_academic'

    if any(k in role for k in ['professor', 'prof.', 'chair ', 'endowed']):
        if 'visiting' not in role and 'adjunct' not in role:
            return 'tenure_track'
    if any(k in role for k in ['lecturer', 'instructor', 'reader', 'senior lecturer']):
        if 'visiting' not in role:
            return 'tenure_track'

    if any(k in role for k in ['postdoc', 'post-doc', 'post doc',
            'visiting professor', 'visiting researcher', 'visiting scholar',
            'visiting assistant', 'research associate', 'research fellow',
            'junior researcher', 'adjunct']):
        return 'postdoc'

    if any(k in org for k in GOV_KW):
        return 'government'

    if any(k in role for k in ['researcher', 'scientist', 'research engineer',
            'senior researcher', 'principal investigator', 'group leader',
            'team leader', 'head of']):
        if 'postdoc' not in role and 'visiting' not in role:
            return 'permanent_research'

    if any(k in role for k in ['senior engineer', 'senior developer', 'senior scientist',
            'staff engineer', 'principal engineer', 'director', 'vp ',
            'vice president', 'cto', 'ceo', 'chief', 'manager', 'lead', 'partner']):
        return 'industry_senior'

    if any(k in role for k in ['engineer', 'developer', 'programmer', 'analyst',
            'data scientist', 'consultant', 'software', 'machine learning',
            'quantitative', 'trader']):
        return 'industry_entry'

    if role == '' or role == 'nan':
        if dtype == 'employment':
            return 'null_industry'
        return 'unknown'
    if dtype == 'employment':
        return 'null_industry'
    if dtype == 'education':
        return 'null_academic'
    return 'unknown'


def classify_tier(role_to, dest_type, dest, llm_tiers=None):
    """Classify tier using LLM mapping first, then fallback."""
    if llm_tiers:
        role = str(role_to).lower().strip() if pd.notna(role_to) else ''
        if role in llm_tiers:
            tier = llm_tiers[role]
            if tier in TIER_SCORES:
                return tier
    return classify_tier_fallback(role_to, dest_type, dest)


# ═══════════════════════════════════════════════════════════
# FIELD SCORING
# ═══════════════════════════════════════════════════════════

def normalize_school(name):
    """Normalize school/institution name for deduplication."""
    if not isinstance(name, str):
        return name
    s = name.lower().strip()
    s = re.sub(r'^the\s+', '', s)               # remove leading "the"
    s = re.sub(r'\s*\([^)]*\)\s*', ' ', s)      # remove parenthetical
    s = re.sub(r'[,.:;]+', '', s)                # remove punctuation
    s = re.sub(r'[-\u2013\u2014]+', ' ', s)      # normalize dashes
    s = re.sub(r'\bat\b', '', s)                 # remove "at" (univ of X at Y)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def compute_field(edges, dest_prestige, node_comms, field, indeg_df, springrank_scores, llm_tiers=None):
    """Compute ranking for one field."""
    print(f"\n{'='*60}")
    print(f"  {field.upper()} v1.3")
    print(f"{'='*60}")

    # ── Normalize school and dest names to deduplicate ──
    schools_before = edges['phd_school'].nunique()
    edges['phd_school'] = edges['phd_school'].apply(normalize_school)
    edges['dest'] = edges['dest'].apply(normalize_school)
    schools_after = edges['phd_school'].nunique()

    n_edges = len(edges)
    n_people = edges['person_orcid'].nunique()
    print(f"  {n_edges:,} edges, {n_people:,} graduates")
    print(f"  Schools: {schools_before:,} -> {schools_after:,} (deduped {schools_before - schools_after:,})")

    # Exclude further_education destinations
    edges['tier'] = edges.apply(
        lambda r: classify_tier(r['role_to'], r['dest_type'], r['dest'], llm_tiers),
        axis=1
    )
    fe_count = (edges['tier'] == 'further_education').sum()
    edges = edges[edges['tier'] != 'further_education'].copy()
    print(f"  Excluded {fe_count} further_education edges")
    print(f"  After: {len(edges):,} edges, {edges['person_orcid'].nunique():,} graduates")

    # ── D score: SpringRank-based dest prestige ──
    # Uses log(indegree) × source_quality — no OpenAlex needed
    edges['dest_prestige_norm'] = edges['dest'].map(dest_prestige).fillna(0)
    matched = (edges['dest_prestige_norm'] > 0).sum()
    print(f"\n  Dest prestige coverage: {matched}/{len(edges)} ({100*matched/len(edges):.1f}%)")

    # Impute remaining unmatched by career tier (small companies/startups)
    matched_vals = edges.loc[edges['dest_prestige_norm'] > 0, 'dest_prestige_norm']
    if len(matched_vals) > 0:
        p10 = matched_vals.quantile(0.10)
        p25 = matched_vals.quantile(0.25)
        p40 = matched_vals.quantile(0.40)
    else:
        p10, p25, p40 = 0.1, 0.2, 0.3
    TIER_IMPUTE = {
        'tenure_track': p25, 'permanent_research': p25,
        'industry_senior': p40, 'industry_entry': p25,
        'government': p25, 'postdoc': p25,
        'null_academic': p10, 'null_industry': p10, 'unknown': p10,
    }
    unmatched_mask = edges['dest_prestige_norm'] == 0
    n_imputed = unmatched_mask.sum()
    edges.loc[unmatched_mask, 'dest_prestige_norm'] = edges.loc[unmatched_mask, 'tier'].map(TIER_IMPUTE).fillna(p10)
    print(f"  Imputed: {n_imputed} edges (sr→P40={p40:.3f}, entry→P25={p25:.3f}, null→P10={p10:.3f})")

    edges['is_intl'] = (edges['dest_country'] != edges['phd_country']).astype(int)

    # Tier × Region crossing: edges that cross both community AND prestige tier
    # are hierarchy-driven (most impressive). Same community + same tier = community-driven.
    edges['school_comm'] = edges['phd_school'].map(node_comms).fillna(-1).astype(int)
    edges['dest_comm'] = edges['dest'].map(node_comms).fillna(-2).astype(int)
    edges['school_sr'] = edges['phd_school'].map(springrank_scores).fillna(0)
    edges['dest_sr'] = edges['dest'].map(springrank_scores).fillna(0)

    # Define prestige tiers from SpringRank
    sr_p75 = np.percentile([v for v in springrank_scores.values()], 75)
    sr_p50 = np.percentile([v for v in springrank_scores.values()], 50)
    def sr_tier(score):
        if score >= sr_p75:
            return 2  # elite
        elif score >= sr_p50:
            return 1  # mid
        return 0      # base

    edges['school_tier'] = edges['school_sr'].apply(sr_tier)
    edges['dest_tier'] = edges['dest_sr'].apply(sr_tier)

    cross_region = (edges['school_comm'] != edges['dest_comm']).astype(int)
    cross_tier = (edges['dest_tier'] != edges['school_tier']).astype(int)

    # Quality multiplier: cross-region AND/OR cross-tier placements get bonus
    # Same region + same tier = 0.90 (community discount)
    # Same region + cross tier = 1.00 (neutral)
    # Cross region + same tier = 1.05 (mild bonus)
    # Cross region + cross tier = 1.10 (hierarchy signal)
    edges['edge_quality'] = 0.90 + 0.10 * cross_region + 0.10 * cross_tier

    edges['D_i'] = edges['dest_prestige_norm'] * edges['edge_quality'] * (1 + INTL_ALPHA * edges['is_intl'])

    # ── T score: tier × dest_prestige, with concentration cap ──
    edges['T_i'] = edges['tier'].map(TIER_SCORES).fillna(0.5)
    edges['T_weighted'] = edges['T_i'] * (0.5 + 0.5 * edges['dest_prestige_norm'])

    # ── Flags (compute with normalized names) ──
    edges['is_self'] = (edges['dest'] == edges['phd_school']).astype(int)

    # Apply concentration cap per school
    # Count dest frequency within each school, cap at CONC_CAP
    dest_counts = edges.groupby(['phd_school', 'dest']).size().reset_index(name='_cnt')
    school_totals = edges.groupby('phd_school').size().reset_index(name='_total')
    dest_counts = dest_counts.merge(school_totals, on='phd_school')
    dest_counts['_share'] = dest_counts['_cnt'] / dest_counts['_total']
    dest_counts['conc_weight'] = np.minimum(dest_counts['_share'], CONC_CAP) / dest_counts['_share']
    edges = edges.merge(dest_counts[['phd_school', 'dest', 'conc_weight']],
                        on=['phd_school', 'dest'], how='left')
    edges['conc_weight'] = edges['conc_weight'].fillna(1.0)
    edges['T_capped'] = edges['T_weighted'] * edges['conc_weight']

    # ── Tier distribution ──
    print(f"\n  Tiers:")
    for t, n in edges['tier'].value_counts().items():
        print(f"    {t:25s} {n:7d} ({100*n/len(edges):5.1f}%)")

    # ── Aggregate per school ──
    g = edges.groupby(['phd_school', 'phd_country'])
    s = g.agg(
        n=('person_orcid', 'nunique'),
        n_dest=('dest', 'nunique'),
        D_raw=('D_i', 'mean'),
        T_raw=('T_capped', 'mean'),
        intl_rate=('is_intl', 'mean'),
        self_ret=('is_self', 'mean'),
        avg_dest_prestige=('dest_prestige_norm', 'mean'),
    ).reset_index()

    # ── Bayesian shrinkage ──
    mu_D = s['D_raw'].mean()
    s['D'] = (s['n'] * s['D_raw'] + SHRINKAGE_K * mu_D) / (s['n'] + SHRINKAGE_K)
    mu_T = s['T_raw'].mean()
    s['T'] = (s['n'] * s['T_raw'] + SHRINKAGE_K * mu_T) / (s['n'] + SHRINKAGE_K)

    # ── R score: return penalty ──
    s['R'] = (1.0 - 0.7 * s['self_ret']).clip(0, 1)

    # ── I score: dual regime using SpringRank prestige ──
    # SpringRank on global placement network: size-independent prestige
    # Also use indegree for destination prestige (100% coverage)
    indeg_map = indeg_df.set_index('dest')['indegree'].to_dict()
    edges['dest_indegree'] = edges['dest'].map(indeg_map).fillna(0)
    edges['dest_indeg_log'] = np.log1p(edges['dest_indegree'])
    max_indeg = edges['dest_indeg_log'].max()
    if max_indeg > 0:
        edges['dest_indeg_norm'] = edges['dest_indeg_log'] / max_indeg
    else:
        edges['dest_indeg_norm'] = 0

    # School prestige from SpringRank (size-independent)
    s['school_springrank'] = s['phd_school'].map(springrank_scores).fillna(0)

    # Prestigious: top 10% of ranked schools by SpringRank
    eligible = s[s['n'] >= MIN_N]
    prestige_thresh = eligible['school_springrank'].quantile(0.90)
    s['is_prestigious'] = s['school_springrank'] >= prestige_thresh

    n_prest = s[s['is_prestigious'] & (s['n'] >= MIN_N)].shape[0]
    print(f"\n  Prestigious schools (top-10% by SpringRank): {n_prest} (threshold={prestige_thresh:.3f})")

    # For prestigious: retention = % going to equally prestigious dests
    # "Equally prestigious" = dest indegree above median (top 50%)
    indeg_thresh = edges['dest_indeg_norm'].quantile(0.50)
    print(f"  Retention threshold (P50 indeg_norm): {indeg_thresh:.3f}")

    edges['is_prestigious_dest'] = (edges['dest_indeg_norm'] >= indeg_thresh).astype(int)

    retention = edges.groupby(['phd_school', 'phd_country'])['is_prestigious_dest'].mean().reset_index()
    retention.columns = ['phd_school', 'phd_country', 'retention']
    s = s.merge(retention, on=['phd_school', 'phd_country'], how='left')
    s['retention'] = s['retention'].fillna(0.5)

    # For non-prestigious: uplift percentile (dest prestige - school prestige)
    # Use SpringRank for school prestige, indegree for dest prestige
    edges['school_springrank'] = edges['phd_school'].map(springrank_scores).fillna(0)
    # Normalize SpringRank to [0,1] for uplift calculation
    sr_min = edges['school_springrank'].min()
    sr_max = edges['school_springrank'].max()
    sr_range = sr_max - sr_min if sr_max > sr_min else 1
    edges['school_sr_norm'] = (edges['school_springrank'] - sr_min) / sr_range
    edges['uplift'] = edges['dest_indeg_norm'] - edges['school_sr_norm']
    uplift_by_school = edges.groupby(['phd_school', 'phd_country'])['uplift'].mean().reset_index()
    uplift_by_school.columns = ['phd_school', 'phd_country', 'uplift_raw']
    s = s.merge(uplift_by_school, on=['phd_school', 'phd_country'], how='left')

    # I score: prestigious → retention, others → uplift percentile
    s['I'] = np.where(
        s['is_prestigious'],
        s['retention'],
        s['uplift_raw'].rank(pct=True)
    )

    # ── Variety bonus ──
    # Schools with diverse outcomes (grads to academia + industry + policy) are rewarded
    # Schools with monotone outcomes (all to same type/tier) are penalized
    n_unique_dest = edges.groupby(['phd_school', 'phd_country'])['dest'].nunique().reset_index()
    n_unique_dest.columns = ['phd_school', 'phd_country', 'n_unique_dest']
    s = s.merge(n_unique_dest, on=['phd_school', 'phd_country'], how='left')
    # Normalized destination entropy (how spread out are grad destinations?)
    def dest_entropy(group):
        counts = group['dest'].value_counts()
        probs = counts / counts.sum()
        H = -(probs * np.log(probs + 1e-10)).sum()
        max_H = np.log(max(len(counts), 2))
        return H / max_H if max_H > 0 else 0
    entropy_df = edges.groupby(['phd_school', 'phd_country']).apply(
        dest_entropy, include_groups=False
    ).reset_index()
    entropy_df.columns = ['phd_school', 'phd_country', 'dest_entropy']
    s = s.merge(entropy_df, on=['phd_school', 'phd_country'], how='left')
    # Also: tier diversity (how many different career tiers?)
    tier_div = edges.groupby(['phd_school', 'phd_country'])['tier'].nunique().reset_index()
    tier_div.columns = ['phd_school', 'phd_country', 'n_tiers']
    s = s.merge(tier_div, on=['phd_school', 'phd_country'], how='left')
    s['tier_diversity'] = (s['n_tiers'] / len(TIER_SCORES)).clip(0, 1)
    # Variety = 0.7*dest_entropy + 0.3*tier_diversity
    s['variety'] = 0.7 * s['dest_entropy'].fillna(0.5) + 0.3 * s['tier_diversity'].fillna(0.3)
    LAMBDA_VAR = 0.05
    s['variety_bonus'] = LAMBDA_VAR * s['variety']

    # ── Composite ──
    w = WEIGHTS
    s['composite'] = w['D'] * s['D'] + w['T'] * s['T'] + w['R'] * s['R'] + w['I'] * s['I'] + s['variety_bonus']
    cmin, cmax = s['composite'].min(), s['composite'].max()
    s['score'] = ((s['composite'] - cmin) / (cmax - cmin) * 100).round(2)

    # ── Rank ──
    rk = s[s['n'] >= MIN_N].sort_values('score', ascending=False).reset_index(drop=True)
    rk['rank'] = range(1, len(rk) + 1)

    # ── Tier percentages ──
    tb = edges.groupby(['phd_school', 'phd_country', 'tier'])['person_orcid'].nunique()
    tb = tb.unstack(fill_value=0).reset_index()
    for t in TIER_SCORES:
        if t not in tb.columns:
            tb[t] = 0
    rk = rk.merge(tb, on=['phd_school', 'phd_country'], how='left')
    for t in TIER_SCORES:
        if t in rk.columns:
            rk[f'pct_{t}'] = (rk[t] / rk['n'] * 100).round(1)

    # ── Print top 50 ──
    print(f"\n  {'Rk':>3s}  {'School':<42s} {'C':>2s} {'N':>5s} {'Score':>6s} "
          f"{'D':>5s} {'T':>5s} {'R':>5s} {'I':>5s} {'TT%':>4s} {'PD%':>4s} {'Ind':>4s}")
    print(f"  {'-'*98}")
    for _, r in rk.head(50).iterrows():
        tt = r.get('pct_tenure_track', 0)
        pd_ = r.get('pct_postdoc', 0)
        ind = r.get('pct_industry_senior', 0) + r.get('pct_industry_entry', 0)
        print(f"  {r['rank']:3.0f}  {r['phd_school'][:42]:<42s} {r['phd_country']:>2s} "
              f"{r['n']:5.0f} {r['score']:6.1f} {r['D']:.3f} {r['T']:.3f} {r['R']:.3f} {r['I']:.3f} "
              f"{tt:3.0f}% {pd_:3.0f}% {ind:3.0f}%")

    # ── Face validity ──
    targets = [
        'massachusetts institute of technology', 'stanford university',
        'harvard university', 'princeton university', 'university of cambridge',
        'university of oxford', 'carnegie mellon university',
        'university of california berkeley', 'university of chicago',
        'yale university', 'cornell university', 'california institute of technology',
        'peking university', 'tsinghua university', 'the university of tokyo',
        'seoul national university', 'national university of singapore',
        'columbia university', 'new york university', 'eth zurich',
        'london school of economics and political science',
        'university of toronto', 'university of waterloo',
    ]
    print(f"\n  Face validity:")
    for t in targets:
        row = rk[rk['phd_school'].str.lower() == t.lower()]
        if len(row) == 0:
            row = rk[rk['phd_school'].str.lower().str.contains(t.split()[0], na=False)]
        if len(row):
            r = row.iloc[0]
            pr = '*' if r['is_prestigious'] else ' '
            print(f"    #{r['rank']:3.0f}{pr} {r['phd_school'][:40]:<40s} sc={r['score']:5.1f} "
                  f"N={r['n']:.0f} D={r['D']:.3f} T={r['T']:.3f} I={r['I']:.3f}")
        else:
            print(f"    ???  {t[:40]:<40s} NOT FOUND")

    print(f"\n  Total ranked: {len(rk)} (N>={MIN_N})")
    print(f"  Median N: {rk['n'].median():.0f}, Max N: {rk['n'].max():.0f}")

    # ── Build JSON records ──
    top_d = edges.groupby(['phd_school', 'dest', 'dest_country'])['person_orcid'].nunique().reset_index()
    top_d.columns = ['phd_school', 'dest', 'dest_country', 'cnt']

    recs = []
    for _, r in rk.iterrows():
        sd = top_d[top_d['phd_school'] == r['phd_school']].nlargest(5, 'cnt')
        top5 = [{'o': row['dest'][:55], 'c': row['dest_country'], 'n': int(row['cnt'])}
                for _, row in sd.iterrows()]
        recs.append({
            'r': int(r['rank']), 's': r['phd_school'], 'c': r['phd_country'],
            'n': int(r['n']), 'sc': float(r['score']),
            'D': round(float(r['D']), 3), 'T': round(float(r['T']), 3),
            'R': round(float(r['R']), 3), 'I': round(float(r['I']), 3),
            'pr': bool(r['is_prestigious']),
            'pi': round(float(r['intl_rate']) * 100, 1),
            'tt': round(float(r.get('pct_tenure_track', 0)), 1),
            'pd': round(float(r.get('pct_postdoc', 0)), 1),
            'ind': round(float(r.get('pct_industry_senior', 0) + r.get('pct_industry_entry', 0)), 1),
            'td': top5,
        })

    # ── Build graduates JSON ──
    grads = {}
    for _, r in rk.iterrows():
        key = f"{field}_{r['phd_school']}"
        se = edges[edges['phd_school'] == r['phd_school']]
        grads[key] = [
            {
                'd': row['dest'] if pd.notna(row['dest']) else '',
                'r': row['role_to'] if pd.notna(row['role_to']) else '',
                'c': row['dest_country'] if pd.notna(row['dest_country']) else '',
                'o': row['person_orcid'] if pd.notna(row['person_orcid']) else '',
            }
            for _, row in se.iterrows()
        ]

    return recs, grads


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='PhDRank v1.3 composite scoring')
    parser.add_argument('--data-dir', required=True, help='Directory with parquet files')
    parser.add_argument('--ror-path', default=None, help='Path to ROR JSON')
    parser.add_argument('--output-dir', default=None, help='Output directory (default: data-dir)')
    args = parser.parse_args()

    d = args.data_dir
    out = args.output_dir or d

    print("PhDRank v1.3 — ROR-enhanced name resolution")
    print("=" * 60)

    # Load dest prestige (SpringRank-based, 100% coverage)
    dp_path = os.path.join(d, 'dest_prestige_sr.json')
    with open(dp_path, 'r') as f:
        dest_prestige = json.load(f)
    print(f"  Dest prestige: {len(dest_prestige):,} destinations (SpringRank-based)")

    # Load LLM tier mapping
    tier_csv = os.path.join(d, 'unique_roles_v3_classified.csv')
    llm_tiers = load_tier_mapping(tier_csv)

    # Load dest_indegree (from global_emp_inflow, 100% coverage)
    indeg_path = os.path.join(d, 'dest_indegree.parquet')
    indeg_df = pd.read_parquet(indeg_path)
    # Normalize dest names in indegree to match
    indeg_df['dest'] = indeg_df['dest'].apply(normalize_school)
    indeg_df = indeg_df.groupby('dest')['indegree'].sum().reset_index()
    print(f"  Dest indegree: {len(indeg_df):,} destinations")

    # Load SpringRank scores
    sr_path = os.path.join(d, 'springrank_scores.json')
    if os.path.exists(sr_path):
        with open(sr_path, 'r') as f:
            springrank_scores = json.load(f)
        print(f"  SpringRank scores: {len(springrank_scores):,} institutions")
    else:
        print(f"  WARNING: {sr_path} not found, falling back to indegree for prestige")
        springrank_scores = {}

    # Load community assignments
    comm_path = os.path.join(d, 'node_communities.json')
    if os.path.exists(comm_path):
        with open(comm_path, 'r') as f:
            node_comms = json.load(f)
        print(f"  Node communities: {len(node_comms):,} nodes")
    else:
        print(f"  WARNING: {comm_path} not found, no community discount")
        node_comms = {}

    # Process each field
    all_json = {}
    all_grads = {}

    for field, parquet in [
        ('cs', os.path.join(d, 'phd4_cs.parquet')),
        ('econ', os.path.join(d, 'phd4_econ.parquet')),
        ('math', os.path.join(d, 'phd4_math.parquet')),
    ]:
        if not os.path.exists(parquet):
            print(f"\n  WARNING: {parquet} not found, skipping {field}")
            continue
        try:
            edges = pd.read_parquet(parquet)
            recs, grads = compute_field(edges, dest_prestige, node_comms, field, indeg_df, springrank_scores, llm_tiers)
            all_json[field] = recs
            all_grads.update(grads)
        except Exception as e:
            print(f"\n  ERROR in {field}: {e}")
            import traceback
            traceback.print_exc()

    # Save outputs
    data_json = os.path.join(out, 'ranking_v13.json')
    with open(data_json, 'w') as f:
        json.dump(all_json, f, separators=(',', ':'))
    total = sum(len(v) for v in all_json.values())
    print(f"\nSaved {data_json} ({total} programs)")

    grad_json = os.path.join(out, 'graduates_v13.json')
    with open(grad_json, 'w') as f:
        json.dump(all_grads, f, separators=(',', ':'))
    print(f"Saved {grad_json} ({len(all_grads)} programs with graduate data)")


if __name__ == '__main__':
    main()
