SELECT symbol, name, asset_class, sector, industry, exchange, currency, market_cap
FROM {t}.dim_security
WHERE lower(symbol) LIKE lower(:q) OR lower(name) LIKE lower(:q)
ORDER BY market_cap DESC
LIMIT 20
