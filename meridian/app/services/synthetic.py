"""Deterministic synthetic market data.

One generator serves two sinks:
- APP_MODE=mock → in-memory DataFrames powering every API endpoint
- scripts/seed_synthetic_data.py → INSERTs into fins.meridian.* tables

Everything is seeded from the symbol name so mock and live data agree.
~60 symbols across sectors/asset classes, 5y business-day GBM with regime
shifts, quarterly fundamentals consistent with price level.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

import numpy as np
import pandas as pd

YEARS = 5
_END = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)
DATES = pd.bdate_range(end=_END, periods=YEARS * 261)

# (symbol, name, asset_class, sector, industry, exchange, currency, start_price, drift, vol)
_SECURITIES: list[tuple] = [
    ("AAPL", "Apple Inc.", "equity", "Technology", "Consumer Electronics", "NASDAQ", "USD", 150, 0.18, 0.24),
    ("MSFT", "Microsoft Corp.", "equity", "Technology", "Software", "NASDAQ", "USD", 240, 0.20, 0.22),
    ("NVDA", "NVIDIA Corp.", "equity", "Technology", "Semiconductors", "NASDAQ", "USD", 45, 0.45, 0.48),
    ("AMD", "Advanced Micro Devices", "equity", "Technology", "Semiconductors", "NASDAQ", "USD", 80, 0.22, 0.42),
    ("GOOGL", "Alphabet Inc. A", "equity", "Technology", "Internet Content", "NASDAQ", "USD", 105, 0.16, 0.26),
    ("META", "Meta Platforms", "equity", "Technology", "Internet Content", "NASDAQ", "USD", 220, 0.24, 0.36),
    ("AMZN", "Amazon.com Inc.", "equity", "Consumer Discretionary", "E-Commerce", "NASDAQ", "USD", 110, 0.17, 0.30),
    ("TSLA", "Tesla Inc.", "equity", "Consumer Discretionary", "Auto Manufacturers", "NASDAQ", "USD", 190, 0.20, 0.55),
    ("AVGO", "Broadcom Inc.", "equity", "Technology", "Semiconductors", "NASDAQ", "USD", 480, 0.28, 0.34),
    ("ORCL", "Oracle Corp.", "equity", "Technology", "Software", "NYSE", "USD", 75, 0.19, 0.26),
    ("CRM", "Salesforce Inc.", "equity", "Technology", "Software", "NYSE", "USD", 190, 0.12, 0.30),
    ("ADBE", "Adobe Inc.", "equity", "Technology", "Software", "NASDAQ", "USD", 400, 0.08, 0.30),
    ("INTC", "Intel Corp.", "equity", "Technology", "Semiconductors", "NASDAQ", "USD", 40, -0.05, 0.35),
    ("QCOM", "Qualcomm Inc.", "equity", "Technology", "Semiconductors", "NASDAQ", "USD", 130, 0.10, 0.30),
    ("TXN", "Texas Instruments", "equity", "Technology", "Semiconductors", "NASDAQ", "USD", 160, 0.09, 0.24),
    ("JPM", "JPMorgan Chase", "equity", "Financials", "Banks", "NYSE", "USD", 140, 0.13, 0.24),
    ("BAC", "Bank of America", "equity", "Financials", "Banks", "NYSE", "USD", 32, 0.07, 0.26),
    ("GS", "Goldman Sachs", "equity", "Financials", "Capital Markets", "NYSE", "USD", 330, 0.13, 0.27),
    ("MS", "Morgan Stanley", "equity", "Financials", "Capital Markets", "NYSE", "USD", 85, 0.10, 0.27),
    ("V", "Visa Inc.", "equity", "Financials", "Payments", "NYSE", "USD", 220, 0.13, 0.20),
    ("MA", "Mastercard Inc.", "equity", "Financials", "Payments", "NYSE", "USD", 360, 0.14, 0.21),
    ("BLK", "BlackRock Inc.", "equity", "Financials", "Asset Management", "NYSE", "USD", 700, 0.11, 0.24),
    ("SCHW", "Charles Schwab", "equity", "Financials", "Capital Markets", "NYSE", "USD", 60, 0.08, 0.30),
    ("XOM", "Exxon Mobil", "equity", "Energy", "Oil & Gas Integrated", "NYSE", "USD", 95, 0.10, 0.28),
    ("CVX", "Chevron Corp.", "equity", "Energy", "Oil & Gas Integrated", "NYSE", "USD", 150, 0.08, 0.26),
    ("COP", "ConocoPhillips", "equity", "Energy", "E&P", "NYSE", "USD", 100, 0.10, 0.32),
    ("SLB", "Schlumberger", "equity", "Energy", "Oilfield Services", "NYSE", "USD", 45, 0.06, 0.34),
    ("JNJ", "Johnson & Johnson", "equity", "Healthcare", "Pharma", "NYSE", "USD", 165, 0.05, 0.16),
    ("UNH", "UnitedHealth Group", "equity", "Healthcare", "Health Plans", "NYSE", "USD", 480, 0.11, 0.22),
    ("LLY", "Eli Lilly", "equity", "Healthcare", "Pharma", "NYSE", "USD", 380, 0.30, 0.30),
    ("PFE", "Pfizer Inc.", "equity", "Healthcare", "Pharma", "NYSE", "USD", 40, -0.08, 0.24),
    ("ABBV", "AbbVie Inc.", "equity", "Healthcare", "Pharma", "NYSE", "USD", 140, 0.10, 0.20),
    ("MRK", "Merck & Co.", "equity", "Healthcare", "Pharma", "NYSE", "USD", 105, 0.08, 0.20),
    ("WMT", "Walmart Inc.", "equity", "Consumer Staples", "Discount Stores", "NYSE", "USD", 145, 0.12, 0.18),
    ("PG", "Procter & Gamble", "equity", "Consumer Staples", "Household Products", "NYSE", "USD", 145, 0.07, 0.16),
    ("KO", "Coca-Cola Co.", "equity", "Consumer Staples", "Beverages", "NYSE", "USD", 58, 0.06, 0.15),
    ("COST", "Costco Wholesale", "equity", "Consumer Staples", "Discount Stores", "NASDAQ", "USD", 480, 0.20, 0.20),
    ("HD", "Home Depot", "equity", "Consumer Discretionary", "Home Improvement", "NYSE", "USD", 300, 0.10, 0.24),
    ("MCD", "McDonald's Corp.", "equity", "Consumer Discretionary", "Restaurants", "NYSE", "USD", 265, 0.08, 0.17),
    ("NKE", "Nike Inc.", "equity", "Consumer Discretionary", "Apparel", "NYSE", "USD", 120, -0.03, 0.30),
    ("DIS", "Walt Disney Co.", "equity", "Communication", "Entertainment", "NYSE", "USD", 110, 0.02, 0.28),
    ("NFLX", "Netflix Inc.", "equity", "Communication", "Streaming", "NASDAQ", "USD", 350, 0.25, 0.36),
    ("CAT", "Caterpillar Inc.", "equity", "Industrials", "Machinery", "NYSE", "USD", 240, 0.13, 0.26),
    ("BA", "Boeing Co.", "equity", "Industrials", "Aerospace", "NYSE", "USD", 210, -0.02, 0.36),
    ("HON", "Honeywell Intl", "equity", "Industrials", "Conglomerates", "NASDAQ", "USD", 200, 0.06, 0.20),
    ("UPS", "United Parcel Service", "equity", "Industrials", "Logistics", "NYSE", "USD", 170, -0.02, 0.26),
    ("GE", "GE Aerospace", "equity", "Industrials", "Aerospace", "NYSE", "USD", 110, 0.25, 0.32),
    ("LIN", "Linde plc", "equity", "Materials", "Industrial Gases", "NASDAQ", "USD", 330, 0.13, 0.19),
    ("FCX", "Freeport-McMoRan", "equity", "Materials", "Copper", "NYSE", "USD", 40, 0.08, 0.36),
    ("NEE", "NextEra Energy", "equity", "Utilities", "Utilities", "NYSE", "USD", 75, 0.04, 0.24),
    ("PLD", "Prologis Inc.", "equity", "Real Estate", "Industrial REITs", "NYSE", "USD", 120, 0.05, 0.26),
    ("SPY", "SPDR S&P 500 ETF", "etf", "Broad Market", "Index ETF", "NYSE", "USD", 420, 0.10, 0.16),
    ("QQQ", "Invesco QQQ Trust", "etf", "Broad Market", "Index ETF", "NASDAQ", "USD", 340, 0.14, 0.20),
    ("IWM", "iShares Russell 2000", "etf", "Broad Market", "Index ETF", "NYSE", "USD", 200, 0.05, 0.20),
    ("TLT", "iShares 20+Y Treasury", "etf", "Fixed Income", "Bond ETF", "NASDAQ", "USD", 105, -0.06, 0.16),
    ("GLD", "SPDR Gold Shares", "etf", "Commodities", "Gold", "NYSE", "USD", 175, 0.10, 0.15),
    ("XLF", "Financial Select SPDR", "etf", "Financials", "Sector ETF", "NYSE", "USD", 35, 0.10, 0.20),
    ("XLE", "Energy Select SPDR", "etf", "Energy", "Sector ETF", "NYSE", "USD", 85, 0.08, 0.30),
    ("BTC-USD", "Bitcoin USD", "crypto", "Crypto", "Crypto", "CRYPTO", "USD", 45000, 0.30, 0.60),
    ("ETH-USD", "Ethereum USD", "crypto", "Crypto", "Crypto", "CRYPTO", "USD", 2500, 0.20, 0.70),
    ("ES=F", "E-mini S&P 500 Fut", "future", "Index", "Equity Index", "CME", "USD", 4400, 0.10, 0.16),
    ("CL=F", "WTI Crude Fut", "future", "Energy", "Crude Oil", "NYMEX", "USD", 78, 0.02, 0.38),
    ("EURUSD=X", "EUR/USD", "fx", "FX", "G10", "FX", "USD", 1.08, 0.01, 0.07),
    ("JPY=X", "USD/JPY", "fx", "FX", "G10", "FX", "USD", 140, 0.03, 0.10),
]

_DIVIDEND_PAYERS = {"JNJ", "PG", "KO", "XOM", "CVX", "JPM", "BAC", "INTC", "TXN", "WMT", "MCD", "NEE", "ABBV", "MRK", "CAT", "UPS"}
DEMO_PORTFOLIO = "demo-core"
_PORTFOLIO = {"NVDA": 40, "AAPL": 60, "MSFT": 25, "AMZN": 30, "LLY": 12, "JPM": 35, "COST": 8, "XLE": 90, "GLD": 50, "QQQ": 15}


def _rng(symbol: str, salt: str = "") -> np.random.Generator:
    seed = int(hashlib.sha256(f"{symbol}:{salt}".encode()).hexdigest()[:8], 16)
    return np.random.default_rng(seed)


def securities() -> pd.DataFrame:
    rows = []
    for sym, name, ac, sec, ind, exch, ccy, _p0, _drift, _vol in _SECURITIES:
        p = prices(sym)
        last = float(p["close"].iloc[-1])
        shares = _rng(sym, "sh").integers(80, 4_000) * 1e6
        rows.append(
            dict(symbol=sym, name=name, asset_class=ac, sector=sec, industry=ind,
                 exchange=exch, currency=ccy, market_cap=round(last * shares, 0))
        )
    return pd.DataFrame(rows)


def symbols() -> list[str]:
    return [s[0] for s in _SECURITIES]


@lru_cache(maxsize=128)
def prices(symbol: str) -> pd.DataFrame:
    """Full 5y daily OHLCV for a symbol. Deterministic."""
    spec = next((s for s in _SECURITIES if s[0] == symbol), None)
    if spec is None:
        return pd.DataFrame(columns=["symbol", "trade_date", "open", "high", "low", "close", "adj_close", "volume"])
    sym, _, _, _, _, _, _, p0, drift, vol_ann = spec
    rng = _rng(sym, "px")
    n = len(DATES)
    mu, sig = drift / 252, vol_ann / np.sqrt(252)
    # regime shifts: volatility and drift change at seeded break points
    breaks = np.sort(rng.choice(np.arange(200, n - 200), size=3, replace=False))
    mu_t = np.full(n, mu)
    sig_t = np.full(n, sig)
    for b in breaks:
        mu_t[b:] = mu * rng.uniform(-0.6, 1.6)
        sig_t[b:] = sig * rng.uniform(0.7, 1.8)
    rets = rng.normal(mu_t, sig_t)
    # occasional gap shocks (earnings-like)
    shocks = rng.random(n) < 0.012
    rets[shocks] += rng.normal(0, sig * 6, shocks.sum())
    close = p0 * np.exp(np.cumsum(rets))
    open_ = close * np.exp(-rets) * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    volume = (rng.lognormal(15.5, 0.6, n) * (1 + sig_t / sig)).astype(np.int64)
    div_factor = np.ones(n)
    if sym in _DIVIDEND_PAYERS:
        for q in range(YEARS * 4):
            ex = int(q * n / (YEARS * 4) + rng.integers(10, 40))
            if ex < n:
                div_factor[ex:] *= 0.996  # ~1.6%/yr yield
    adj_close = close * div_factor
    df = pd.DataFrame(
        dict(symbol=sym, trade_date=DATES, open=np.round(open_, 2), high=np.round(high, 2),
             low=np.round(low, 2), close=np.round(close, 2), adj_close=np.round(adj_close, 4),
             volume=volume)
    )
    return df


def price_window(symbol: str, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> pd.DataFrame:
    df = prices(symbol)
    if start is not None:
        df = df[df.trade_date >= start]
    if end is not None:
        df = df[df.trade_date <= end]
    return df


@lru_cache(maxsize=128)
def fundamentals(symbol: str) -> pd.DataFrame:
    """Quarterly fundamentals roughly consistent with price level."""
    spec = next((s for s in _SECURITIES if s[0] == symbol), None)
    if spec is None or spec[2] != "equity":
        return pd.DataFrame()
    rng = _rng(symbol, "fn")
    p = prices(symbol)
    last = float(p["close"].iloc[-1])
    shares = int(_rng(symbol, "sh").integers(80, 4_000) * 1e6)
    ps = float(rng.uniform(1.5, 9.0))
    rev_q = last * shares / ps / 4
    rows = []
    growth = rng.uniform(-0.02, 0.09)
    gm = rng.uniform(0.25, 0.75)
    om = gm - rng.uniform(0.05, 0.30)
    ends = pd.date_range(end=_END, periods=YEARS * 4, freq="QE")
    for i, pe in enumerate(ends):
        rq = rev_q * ((1 + growth) ** i) * rng.normal(1, 0.05)
        gp = rq * gm * rng.normal(1, 0.05)
        oi = rq * om * rng.normal(1, 0.10)
        ni = oi * rng.uniform(0.72, 0.92)
        fcf = ni * rng.uniform(0.8, 1.3)
        debt = rev_q * rng.uniform(0.2, 1.2)
        cash = rev_q * rng.uniform(0.1, 0.8)
        rows.append(dict(symbol=symbol, fiscal_period=f"Q{(i % 4) + 1}", period_end=pe.normalize(),
                         revenue=round(rq), gross_profit=round(gp), operating_income=round(oi),
                         net_income=round(ni), eps_diluted=round(ni / shares, 2),
                         free_cash_flow=round(fcf), total_debt=round(debt), cash=round(cash),
                         shares_out=shares))
    return pd.DataFrame(rows)


def positions(portfolio_id: str = DEMO_PORTFOLIO) -> pd.DataFrame:
    if portfolio_id != DEMO_PORTFOLIO:
        return pd.DataFrame()
    rows = []
    as_of = DATES[-1].date()
    rng = _rng("portfolio")
    for sym, qty in _PORTFOLIO.items():
        p = prices(sym)
        last = float(p["close"].iloc[-1])
        cost = last * float(rng.uniform(0.5, 0.95))
        rows.append(dict(portfolio_id=portfolio_id, symbol=sym, as_of_date=as_of,
                         quantity=qty, cost_basis=round(cost * qty, 2),
                         market_value=round(last * qty, 2)))
    return pd.DataFrame(rows)


_NEWS_TEMPLATES = [
    "{name} beats Q{q} estimates; raises full-year guidance",
    "{name} unveils next-gen product line at annual event",
    "Analysts lift {name} price target after strong results",
    "{name} announces ${b}B share repurchase program",
    "{name} faces margin pressure as input costs rise",
    "Regulators review {name} practices; shares slip",
    "{name} partners with major cloud provider on AI",
]


def news_events(symbol: str) -> pd.DataFrame:
    rng = _rng(symbol, "nw")
    name = next((s[1] for s in _SECURITIES if s[0] == symbol), symbol)
    rows = []
    for _ in range(int(rng.integers(6, 14))):
        ts = DATES[int(rng.integers(0, len(DATES)))] + pd.Timedelta(hours=int(rng.integers(8, 18)))
        t = _NEWS_TEMPLATES[int(rng.integers(0, len(_NEWS_TEMPLATES)))]
        rows.append(dict(symbol=symbol, ts=ts, headline=t.format(name=name, q=int(rng.integers(1, 5)), b=int(rng.integers(2, 40))),
                         source=rng.choice(["Reuters", "Bloomberg", "WSJ", "Dow Jones"]), sentiment_score=float(np.round(rng.normal(0.25, 0.5), 2))))
    return pd.DataFrame(rows).sort_values("ts")


def corp_events(symbol: str) -> pd.DataFrame:
    """Earnings (E) and dividend (D) badges for the time axis."""
    rng = _rng(symbol, "ev")
    rows = []
    f = fundamentals(symbol)
    if not f.empty:
        for _, r in f.iterrows():
            beat = rng.random() > 0.3
            rows.append(dict(symbol=symbol, event_date=(r["period_end"] + pd.Timedelta(days=25)).date(),
                             kind="E", detail=f"EPS {r['eps_diluted']:.2f} — {'beat' if beat else 'miss'}",
                             sentiment="beat" if beat else "miss"))
    if symbol in _DIVIDEND_PAYERS:
        for q in range(YEARS * 4):
            ex = DATES[int(q * len(DATES) / (YEARS * 4)) + 30]
            rows.append(dict(symbol=symbol, event_date=ex.date(), kind="D",
                             detail="Quarterly dividend", sentiment="neutral"))
    return pd.DataFrame(rows)


def table(name: str) -> pd.DataFrame:
    """Full-table view for seeding: dim_security / fact_* / app_*."""
    if name == "dim_security":
        return securities()
    if name == "fact_price_daily":
        return pd.concat([prices(s) for s in symbols()], ignore_index=True)
    if name == "fact_fundamentals_quarterly":
        return pd.concat([f for f in (fundamentals(s) for s in symbols()) if not f.empty], ignore_index=True)
    if name == "fact_portfolio_positions":
        return positions()
    if name == "fact_news_events":
        return pd.concat([news_events(s) for s in symbols()], ignore_index=True)
    if name == "fact_events":
        return pd.concat([corp_events(s) for s in symbols()], ignore_index=True)
    raise KeyError(name)
