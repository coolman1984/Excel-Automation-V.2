-- The rows the dashboard filters (used by the "analytics" block in project.json).
--
-- One flat SELECT over the trusted views: a date column, every column people
-- want to filter or group by, and the raw numbers to add up. The engine
-- pre-aggregates this once per run, so the browser filters by summing cells -
-- it never recalculates a trusted formula.

SELECT m.example_date  AS example_date,
       m.example_group AS example_group,
       m.example_value AS example_value
FROM v_main m;
