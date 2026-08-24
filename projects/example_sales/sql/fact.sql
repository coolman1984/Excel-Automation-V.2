-- The rows the dashboard filters.
--
-- One flat SELECT over the trusted views: a date, the dimensions people want to
-- slice by, and the raw numbers to add up. The engine pre-aggregates this once
-- per run, so the browser can filter by summing - never by recalculating.

SELECT s.invoice_date                      AS invoice_date,
       s.product                           AS product,
       COALESCE(c.segment, 'Unknown')      AS segment,
       COALESCE(c.country, 'Unknown')      AS country,
       s.amount                            AS amount,
       s.quantity                          AS quantity
FROM v_sales s
LEFT JOIN v_customers c ON c.customer_id = s.customer_id;
