-- Trusted calculations for this project.
--
-- Rules:
--   * read the trusted history views (v_<source_id>), never stg__ or clean__;
--   * every metric starts with "-- metric: <id>" followed by its annotations;
--   * "kind" is kpi (one number), series (label/value rows) or table (any columns);
--   * the trusted formula lives here once - the browser only displays the result.

-- metric: record_count
-- kind: kpi
-- title: Records
-- format: integer
SELECT COUNT(*) AS value FROM v_main;
