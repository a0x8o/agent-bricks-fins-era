SELECT r.symbol, d.name, d.sector, r.last,
       CASE :metric_col
         WHEN 'chg_pct_1d' THEN r.ret_1d
         WHEN 'ret_1w' THEN r.ret_1w
         WHEN 'ret_1m' THEN r.ret_1m
         WHEN 'ret_ytd' THEN r.ret_ytd
         ELSE r.ret_1y
       END AS metric,
       d.market_cap
FROM {t}.v_returns r
JOIN {t}.dim_security d ON d.symbol = r.symbol
