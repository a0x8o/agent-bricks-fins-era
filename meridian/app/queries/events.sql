SELECT event_date, kind, detail, sentiment
FROM {t}.fact_events
WHERE symbol = :symbol
ORDER BY event_date
