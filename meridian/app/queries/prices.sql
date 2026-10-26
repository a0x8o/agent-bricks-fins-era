SELECT symbol, trade_date, open, high, low, close, adj_close, volume
FROM {t}.fact_price_daily
WHERE symbol = :symbol
  AND trade_date >= CAST(:start AS DATE)
  AND trade_date <= CAST(:until AS DATE)
ORDER BY trade_date
