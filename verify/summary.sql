-- Recompute reports/audit.json from the seven segment tables it summarises.
--
-- audit.json is the file the README quotes and the figures read. Every field
-- in it is a min, max, ratio or gap over one segment CSV, so the CSVs are the
-- rawer source and the JSON is derived. Nothing in the Python checked that the
-- derivation was right: the same function wrote both.
--
-- This does the aggregation in SQL instead, joins the result against the
-- published JSON by path, and prints a row for every disagreement. A clean run
-- prints only the OK count.
--
-- Run with: sqlite3 -init verify/summary.sql :memory: ""

.bail on
.mode csv
.import --csv reports/segment_amount_band.csv       t_amount_band
.import --csv reports/segment_card_type.csv         t_card_type
.import --csv reports/segment_device_type.csv       t_device_type
.import --csv reports/segment_email_class.csv       t_email_class
.import --csv reports/segment_identity_present.csv  t_identity_present
.import --csv reports/segment_product_code.csv      t_product_code
.import --csv reports/segment_region.csv            t_region
.import --csv reports/impossibility.csv             t_impossibility
.mode list
.headers off

CREATE TEMP VIEW seg AS
  SELECT 'amount_band'      AS segment, * FROM t_amount_band      UNION ALL
  SELECT 'card_type',       * FROM t_card_type       UNION ALL
  SELECT 'device_type',     * FROM t_device_type     UNION ALL
  SELECT 'email_class',     * FROM t_email_class     UNION ALL
  SELECT 'identity_present',* FROM t_identity_present UNION ALL
  SELECT 'product_code',    * FROM t_product_code    UNION ALL
  SELECT 'region',          * FROM t_region;

CREATE TEMP VIEW doc AS SELECT readfile('reports/audit.json') AS j;

-- Aggregate each segment the way disparity() does.
CREATE TEMP VIEW agg AS
SELECT segment,
       COUNT(*)                                   AS n_groups,
       MIN(CAST(selection_rate AS REAL))          AS selection_min,
       MAX(CAST(selection_rate AS REAL))          AS selection_max,
       MIN(CAST(selection_rate AS REAL)) / MAX(CAST(selection_rate AS REAL))
                                                  AS disparate_impact_ratio,
       MIN(CAST(FPR AS REAL))                     AS FPR_min,
       MAX(CAST(FPR AS REAL))                     AS FPR_max,
       MAX(CAST(FPR AS REAL)) / MIN(CAST(FPR AS REAL)) AS FPR_ratio,
       (MAX(CAST(FPR AS REAL)) - MIN(CAST(FPR AS REAL))) * 100 AS FPR_gap_pp,
       (MAX(CAST(FNR AS REAL)) - MIN(CAST(FNR AS REAL))) * 100 AS FNR_gap_pp,
       MIN(CAST(AUC AS REAL))                     AS AUC_min,
       MAX(CAST(AUC AS REAL))                     AS AUC_max,
       SUM(CAST(n AS INTEGER))                    AS rows_covered
FROM seg GROUP BY segment;

-- One (segment, field, recomputed) row per number audit.json publishes.
CREATE TEMP VIEW recomputed AS
  SELECT segment, 'n_groups' AS field, CAST(n_groups AS REAL) AS got FROM agg UNION ALL
  SELECT segment, 'selection_min', selection_min FROM agg UNION ALL
  SELECT segment, 'selection_max', selection_max FROM agg UNION ALL
  SELECT segment, 'disparate_impact_ratio', disparate_impact_ratio FROM agg UNION ALL
  SELECT segment, 'FPR_min', FPR_min FROM agg UNION ALL
  SELECT segment, 'FPR_max', FPR_max FROM agg UNION ALL
  SELECT segment, 'FPR_ratio', FPR_ratio FROM agg UNION ALL
  SELECT segment, 'FPR_gap_pp', FPR_gap_pp FROM agg UNION ALL
  SELECT segment, 'FNR_gap_pp', FNR_gap_pp FROM agg UNION ALL
  SELECT segment, 'AUC_min', AUC_min FROM agg UNION ALL
  SELECT segment, 'AUC_max', AUC_max FROM agg;

CREATE TEMP VIEW compared AS
SELECT r.segment, r.field, r.got,
       CAST(json_extract(d.j, '$.segments.' || r.segment || '.' || r.field) AS REAL) AS want
FROM recomputed r, doc d;

-- Numeric fields.
SELECT 'FAIL ' || segment || '.' || field ||
       ': SQL ' || format('%.17g', got) || ', audit.json ' || format('%.17g', want)
FROM compared
WHERE want IS NULL
   OR abs(got - want) > 1e-9 * max(1.0, abs(want));

-- The group names attached to the extreme FPRs.
SELECT 'FAIL ' || segment || '.worst_FPR_group: SQL ' || g || ', audit.json ' || w
FROM (
  SELECT s.segment AS segment, s."group" AS g,
         json_extract(d.j, '$.segments.' || s.segment || '.worst_FPR_group') AS w
  FROM seg s, agg a, doc d
  WHERE s.segment = a.segment AND CAST(s.FPR AS REAL) = a.FPR_max
) WHERE g IS NOT w;

SELECT 'FAIL ' || segment || '.best_FPR_group: SQL ' || g || ', audit.json ' || w
FROM (
  SELECT s.segment AS segment, s."group" AS g,
         json_extract(d.j, '$.segments.' || s.segment || '.best_FPR_group') AS w
  FROM seg s, agg a, doc d
  WHERE s.segment = a.segment AND CAST(s.FPR AS REAL) = a.FPR_min
) WHERE g IS NOT w;

-- The four-fifths verdict, and the claim that every segment fails it.
SELECT 'FAIL ' || a.segment || '.passes_four_fifths: SQL ' ||
       (a.disparate_impact_ratio >= 0.8) || ', audit.json ' ||
       (json_extract(d.j, '$.segments.' || a.segment || '.passes_four_fifths') = 1)
FROM agg a, doc d
WHERE (a.disparate_impact_ratio >= 0.8)
   <> (json_extract(d.j, '$.segments.' || a.segment || '.passes_four_fifths') = 1);

-- Every segment must cover the whole audit, no group silently dropped.
SELECT 'FAIL ' || a.segment || ': groups cover ' || a.rows_covered ||
       ' rows, audit.json n is ' || json_extract(d.j, '$.n')
FROM agg a, doc d WHERE a.rows_covered <> json_extract(d.j, '$.n');

-- The impossibility block: the two equalising targets are the mean of the
-- global-threshold policy's per-group rates.
SELECT 'FAIL impossibility.' || field || ': SQL ' || format('%.17g', got) ||
       ', audit.json ' || format('%.17g', want)
FROM (
  SELECT 'target_selection' AS field,
         avg(CAST(selection_rate AS REAL)) AS got,
         (SELECT CAST(json_extract(j, '$.impossibility.target_selection') AS REAL) FROM doc) AS want
  FROM t_impossibility WHERE policy = 'global threshold'
  UNION ALL
  SELECT 'target_fpr', avg(CAST(FPR AS REAL)),
         (SELECT CAST(json_extract(j, '$.impossibility.target_fpr') AS REAL) FROM doc)
  FROM t_impossibility WHERE policy = 'global threshold'
) WHERE abs(got - want) > 1e-9 * max(1.0, abs(want));

-- The global-threshold rows of impossibility.csv are the product_code segment
-- table measured again. They must agree row for row.
SELECT 'FAIL cross-file product_code/' || i."group" || ' ' || which
FROM (
  SELECT i."group" AS "group", 'selection_rate' AS which,
         CAST(i.selection_rate AS REAL) - CAST(p.selection_rate AS REAL) AS d
  FROM t_impossibility i JOIN t_product_code p ON i."group" = p."group"
  WHERE i.policy = 'global threshold'
  UNION ALL
  SELECT i."group", 'FPR', CAST(i.FPR AS REAL) - CAST(p.FPR AS REAL)
  FROM t_impossibility i JOIN t_product_code p ON i."group" = p."group"
  WHERE i.policy = 'global threshold'
  UNION ALL
  SELECT i."group", 'TPR', CAST(i.TPR AS REAL) - CAST(p.TPR AS REAL)
  FROM t_impossibility i JOIN t_product_code p ON i."group" = p."group"
  WHERE i.policy = 'global threshold'
  UNION ALL
  SELECT i."group", 'base_rate', CAST(i.base_rate AS REAL) - CAST(p.base_rate AS REAL)
  FROM t_impossibility i JOIN t_product_code p ON i."group" = p."group"
  WHERE i.policy = 'global threshold'
  UNION ALL
  SELECT i."group", 'n', CAST(i.n AS REAL) - CAST(p.n AS REAL)
  FROM t_impossibility i JOIN t_product_code p ON i."group" = p."group"
  WHERE i.policy = 'global threshold'
) i WHERE abs(d) > 1e-12;

-- And the threshold that produced them is the one audit.json publishes.
SELECT 'FAIL global threshold ' || format('%.17g', CAST(threshold AS REAL)) ||
       ' does not match audit.json ' ||
       format('%.17g', (SELECT CAST(json_extract(j, '$.threshold') AS REAL) FROM doc))
FROM t_impossibility WHERE policy = 'global threshold'
  AND abs(CAST(threshold AS REAL)
          - (SELECT CAST(json_extract(j, '$.threshold') AS REAL) FROM doc)) > 1e-15;

SELECT 'SQL: ' || (SELECT COUNT(*) FROM compared) ||
       ' numeric fields over ' || (SELECT COUNT(DISTINCT segment) FROM agg) ||
       ' segments, plus the impossibility block, recomputed from the segment' ||
       ' tables; worst relative residual ' ||
       format('%.1e', (SELECT max(abs(got - want) / max(1.0, abs(want))) FROM compared)) ||
       ' (tolerance 1.0e-09)';
.quit
