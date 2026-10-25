SELECT p.symbol, d.name, d.sector, p.quantity, p.cost_basis, p.market_value,
       r.last, r.last * p.quantity - p.cost_basis AS unrealized_pnl,
       p.market_value / total.total_mv AS weight
FROM {t}.fact_portfolio_positions p
JOIN {t}.dim_security d ON d.symbol = p.symbol
JOIN {t}.v_returns r ON r.symbol = p.symbol
CROSS JOIN (SELECT sum(market_value) AS total_mv
            FROM {t}.fact_portfolio_positions WHERE portfolio_id = :portfolio_id) total
WHERE p.portfolio_id = :portfolio_id
ORDER BY weight DESC
