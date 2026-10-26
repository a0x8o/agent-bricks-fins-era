SELECT r.symbol, d.name, r.last, r.last - r.prev_close AS change,
       r.ret_1d AS change_pct, d.currency, r.as_of,
       r.ret_1w, r.ret_1m, r.ret_3m, r.ret_6m, r.ret_ytd, r.ret_1y
FROM {t}.v_returns r
JOIN {t}.dim_security d ON d.symbol = r.symbol
WHERE r.symbol = :symbol
