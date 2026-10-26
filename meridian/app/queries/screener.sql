SELECT r.symbol, d.name, d.sector, d.asset_class, r.last, r.ret_1d AS chg_pct_1d,
       r.ret_1m, r.ret_1y, d.market_cap
FROM {t}.v_returns r
JOIN {t}.dim_security d ON d.symbol = r.symbol
WHERE (:sector = '' OR d.sector = :sector)
ORDER BY d.market_cap DESC
