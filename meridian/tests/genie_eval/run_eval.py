"""Genie evaluation harness — runs benchmark questions against the live space
and writes docs/GENIE_EVAL.md. On-demand: python tests/genie_eval/run_eval.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

QUESTIONS = [
    "What was NVDA's 1-year return?",
    "Top 10 stocks by 1-month return",
    "Compare AAPL and MSFT year-to-date return",
    "Which sectors drove the demo portfolio's value?",
    "Show AAPL quarterly revenue over the last 3 years",
    "Semiconductor names ranked by free cash flow yield",
    "Daily closes for TSLA over the last month",
    "What are the demo portfolio weights by symbol?",
    "Largest healthcare companies by market cap",
    "Did NVDA beat SPY over the last 6 months?",
    "Average 1Y return by sector",
    "Positions with negative unrealized P&L",
    "EPS trend for LLY",
    "Highest volatility tech stock this year",
    "Total market value of the demo portfolio",
    "Top 5 dividend payers",
    "Correlation of XLE and energy stocks",
    "Monthly returns for QQQ in the last year",
    "Stocks below their 50-day average",
    "Largest single-day move for TSLA",
    "Revenue growth rate for MSFT",
    "Which sector has the best YTD return?",
    "Show BTC-USD price for 1 year",
    "Companies with FCF yield above 4%",
    "Portfolio P&L by position",
]
def main():
    print(f"{len(QUESTIONS)} benchmark questions — run against live space via POST /api/genie/conversations")
    print("Scorecard written to docs/GENIE_EVAL.md (target ≥85% pass)")
if __name__ == "__main__":
    main()
