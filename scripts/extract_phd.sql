-- ============================================================
-- Extract field edges with ALL columns for composite scoring
-- Run from sodenkai directory: .read extract_full.sql
-- ============================================================

-- CS
COPY (
    SELECT
        org_from AS phd_school,
        org_country_from AS phd_country,
        org_dept_from AS phd_dept,
        org_to AS dest,
        org_country_to AS dest_country,
        role_to,
        role_type_to AS dest_type,
        role_from,
        role_type_from,
        org_dept_to AS dest_dept,
        person_orcid,
        epi_end_year_from AS phd_end_year,
        epi_start_year_to AS dest_start_year
    FROM read_parquet('orcid/edges/aff.parquet')
    WHERE role_type_from = 'education'
      AND org_from != org_to
      AND (lower(org_dept_from) LIKE '%computer%'
        OR lower(org_dept_from) LIKE '%informatic%'
        OR lower(org_dept_from) LIKE '%computing%'
        OR lower(org_dept_from) LIKE '%artificial intelligence%'
        OR lower(org_dept_from) LIKE '%machine learning%'
        OR lower(org_dept_from) LIKE '%data science%'
        OR lower(org_dept_from) LIKE '%software engineer%'
        OR lower(org_dept_from) LIKE '%情報%')
) TO 'full_cs.parquet' (FORMAT PARQUET);

-- Econ
COPY (
    SELECT
        org_from AS phd_school,
        org_country_from AS phd_country,
        org_dept_from AS phd_dept,
        org_to AS dest,
        org_country_to AS dest_country,
        role_to,
        role_type_to AS dest_type,
        role_from,
        role_type_from,
        org_dept_to AS dest_dept,
        person_orcid,
        epi_end_year_from AS phd_end_year,
        epi_start_year_to AS dest_start_year
    FROM read_parquet('orcid/edges/aff.parquet')
    WHERE role_type_from = 'education'
      AND org_from != org_to
      AND (lower(org_dept_from) LIKE '%econom%'
        OR lower(org_dept_from) LIKE '%経済%'
        OR lower(org_dept_from) LIKE '%political economy%')
) TO 'full_econ.parquet' (FORMAT PARQUET);

-- Math
COPY (
    SELECT
        org_from AS phd_school,
        org_country_from AS phd_country,
        org_dept_from AS phd_dept,
        org_to AS dest,
        org_country_to AS dest_country,
        role_to,
        role_type_to AS dest_type,
        role_from,
        role_type_from,
        org_dept_to AS dest_dept,
        person_orcid,
        epi_end_year_from AS phd_end_year,
        epi_start_year_to AS dest_start_year
    FROM read_parquet('orcid/edges/aff.parquet')
    WHERE role_type_from = 'education'
      AND org_from != org_to
      AND (lower(org_dept_from) LIKE '%mathematic%'
        OR lower(org_dept_from) LIKE '%数学%'
        OR lower(org_dept_from) LIKE '%applied math%')
) TO 'full_math.parquet' (FORMAT PARQUET);

-- Pre-PhD origins (education → education edges, for input quality control)
COPY (
    SELECT
        org_to AS phd_school,
        org_from AS prior_school,
        org_country_from AS prior_country,
        role_from AS prior_role,
        person_orcid
    FROM read_parquet('orcid/edges/aff.parquet')
    WHERE role_type_from = 'education'
      AND role_type_to = 'education'
      AND org_from != org_to
) TO 'prior_origins.parquet' (FORMAT PARQUET);

-- Global destination indegree (for prestige score)
COPY (
    SELECT
        org_to AS dest,
        COUNT(DISTINCT person_orcid) AS indegree
    FROM read_parquet('orcid/edges/aff.parquet')
    WHERE role_type_from = 'education'
      AND org_from != org_to
    GROUP BY org_to
) TO 'dest_indegree.parquet' (FORMAT PARQUET);

.print 'Extraction complete. Files: full_cs.parquet, full_econ.parquet, full_math.parquet, prior_origins.parquet, dest_indegree.parquet'
