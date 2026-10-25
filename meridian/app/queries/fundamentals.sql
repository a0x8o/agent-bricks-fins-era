SELECT symbol, fiscal_period, period_end, revenue, gross_profit, operating_income,
       net_income, eps_diluted, free_cash_flow, total_debt, cash, shares_out
FROM {t}.fact_fundamentals_quarterly
WHERE symbol = :symbol
ORDER BY period_end
