"""Market-data seam — dispatches to synthetic (mock) or SQL (live).

Every router calls these functions; mock vs live is decided here so routers,
tests, and the frontend never know which backend served the data.
"""

from __future__ import annotations

import pandas as pd

from ..auth import Identity
from ..config import get_settings
from ..models.schemas import Bar, Column, ResultSet, SecurityOut
from . import synthetic
from .sql_exec import run_query

_INTERVAL_DAYS = {
    "1D": 2, "5D": 7, "1M": 31, "3M": 93, "6M": 186,
    "YTD": None, "1Y": 366, "5Y": 1831, "ALL": None,
}
ALLOWED_INTERVALS = {"1m", "5m", "15m", "1h", "1D", "1W", "1M"}
ALLOWED_RANGES = set(_INTERVAL_DAYS)


def _range_start(range_: str) -> pd.Timestamp | None:
    if range_ == "YTD":
        return pd.Timestamp(pd.Timestamp.today().year, 1, 1)
    d = _INTERVAL_DAYS.get(range_)
    return pd.Timestamp.today().normalize() - pd.Timedelta(days=d) if d else None


def search_securities(query: str, identity: Identity) -> tuple[list[SecurityOut], bool]:
    if get_settings().mock:
        df = synthetic.securities()
        q = query.lower()
        df = df[df.symbol.str.lower().str.contains(q) | df.name.str.lower().str.contains(q)]
        return [SecurityOut(**r) for r in df.head(20).to_dict("records")], False
    rs, hit = run_query("securities_search", {"q": f"%{query}%"}, identity)
    return [SecurityOut(**{c.name: r[i] for i, c in enumerate(rs.columns)}) for r in rs.rows], hit


def get_bars(symbol: str, range_: str, interval: str, until: str | None,
             identity: Identity) -> tuple[list[Bar], str | None, bool]:
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(f"interval must be one of {sorted(ALLOWED_INTERVALS)}")
    if range_ not in ALLOWED_RANGES:
        raise ValueError(f"range must be one of {sorted(ALLOWED_RANGES)}")
    if get_settings().mock:
        df = synthetic.price_window(symbol, _range_start(range_),
                                    pd.Timestamp(until) if until else None)
        bars = [
            Bar(time=r.trade_date.date().isoformat(), open=r.open, high=r.high,
                low=r.low, close=r.close, adj_close=r.adj_close, volume=int(r.volume))
            for r in df.itertuples()
        ]
        as_of = str(df.trade_date.max().date()) if len(df) else None
        return bars, as_of, False
    rs, hit = run_query(
        "prices",
        {"symbol": symbol, "interval": interval,
         "start": str(_range_start(range_).date()) if _range_start(range_) is not None else "1900-01-01",
         "until": until or "9999-12-31"},
        identity,
    )
    bars = [
        Bar(time=str(r[1])[:10], open=float(r[2]), high=float(r[3]), low=float(r[4]),
            close=float(r[5]), adj_close=float(r[6]), volume=int(r[7]))
        for r in rs.rows
    ]
    return bars, str(rs.rows[-1][1])[:10] if rs.rows else None, hit


def get_quote(symbol: str, identity: Identity, until: str | None = None) -> tuple[dict, bool]:
    if get_settings().mock:
        df = synthetic.prices(symbol)
        if until:
            df = df[df.trade_date <= pd.Timestamp(until)]
        sec = synthetic.securities().set_index("symbol").loc[symbol]
        last = float(df.close.iloc[-1])
        prev = float(df.close.iloc[-2])

        def ret(days: int) -> float | None:
            idx = df.index[df.trade_date <= df.trade_date.iloc[-1] - pd.Timedelta(days=days)]
            if len(idx) == 0:
                return None
            base = float(df.loc[idx[-1], "close"])
            return round((last / base - 1) * 100, 2)

        ytd_base = df[df.trade_date < pd.Timestamp(pd.Timestamp.today().year, 1, 1)]
        ytd = round((last / float(ytd_base.close.iloc[-1]) - 1) * 100, 2) if len(ytd_base) else None
        return dict(
            symbol=symbol, name=sec["name"], last=round(last, 2),
            change=round(last - prev, 2), change_pct=round((last / prev - 1) * 100, 2),
            currency=sec["currency"], market_status="closed",
            perf=dict(w1=ret(7), m1=ret(31), m3=ret(93), m6=ret(186), ytd=ytd, y1=ret(365)),
            news_headline=None, as_of=str(df.trade_date.iloc[-1].date()),
        ), False
    rs, hit = run_query("quote", {"symbol": symbol}, identity)
    row = rs.rows[0] if rs.rows else []
    vals = {c.name: row[i] for i, c in enumerate(rs.columns)} if row else {}
    return vals, hit


def get_fundamentals(symbol: str, identity: Identity) -> tuple[ResultSet, bool]:
    if get_settings().mock:
        df = synthetic.fundamentals(symbol)
        return _df_result(df), False
    return run_query("fundamentals", {"symbol": symbol}, identity)


def get_portfolio(portfolio_id: str, identity: Identity) -> tuple[ResultSet, bool]:
    if get_settings().mock:
        df = synthetic.positions(portfolio_id)
        return _df_result(df), False
    return run_query("portfolio", {"portfolio_id": portfolio_id}, identity)


def get_screener(sector: str | None, identity: Identity) -> tuple[ResultSet, bool]:
    if get_settings().mock:
        sec = synthetic.securities()
        if sector:
            sec = sec[sec.sector == sector]
        rows = []
        for _, s in sec.iterrows():
            df = synthetic.prices(s.symbol)
            if df.empty:
                continue
            last, prev = float(df.close.iloc[-1]), float(df.close.iloc[-2])
            m1 = df[df.trade_date <= df.trade_date.iloc[-1] - pd.Timedelta(days=31)]
            m1r = (last / float(m1.close.iloc[-1]) - 1) * 100 if len(m1) else None
            y1 = df[df.trade_date <= df.trade_date.iloc[-1] - pd.Timedelta(days=365)]
            y1r = (last / float(y1.close.iloc[-1]) - 1) * 100 if len(y1) else None
            rows.append([s.symbol, s["name"], s.sector, s.asset_class, round(last, 2),
                         round((last / prev - 1) * 100, 2),
                         round(m1r, 2) if m1r is not None else None,
                         round(y1r, 2) if y1r is not None else None,
                         s.market_cap])
        return ResultSet(
            columns=[Column(name=n, type=t) for n, t in [
                ("symbol", "STRING"), ("name", "STRING"), ("sector", "STRING"),
                ("asset_class", "STRING"), ("last", "DOUBLE"), ("chg_pct_1d", "DOUBLE"),
                ("ret_1m", "DOUBLE"), ("ret_1y", "DOUBLE"), ("market_cap", "DOUBLE")]],
            rows=rows, row_count=len(rows)), False
    return run_query("screener", {"sector": sector or ""}, identity)


def get_heatmap(metric: str, identity: Identity) -> tuple[ResultSet, bool]:
    allowed = {"1d": "chg_pct_1d", "1w": "ret_1w", "1m": "ret_1m", "ytd": "ret_ytd", "1y": "ret_1y"}
    col = allowed.get(metric, "ret_1m")
    if get_settings().mock:
        sec = synthetic.securities()
        rows = []
        for _, s in sec.iterrows():
            df = synthetic.prices(s.symbol)
            if df.empty:
                continue
            last = float(df.close.iloc[-1])
            days = {"1d": 1, "1w": 7, "1m": 31, "ytd": None, "1y": 365}[metric]
            if days is None:
                base_df = df[df.trade_date < pd.Timestamp(pd.Timestamp.today().year, 1, 1)]
            else:
                base_df = df[df.trade_date <= df.trade_date.iloc[-1] - pd.Timedelta(days=days)]
            r = (last / float(base_df.close.iloc[-1]) - 1) * 100 if len(base_df) else 0.0
            rows.append([s.symbol, s["name"], s.sector, round(last, 2), round(r, 2), s.market_cap])
        return ResultSet(
            columns=[Column(name=n, type=t) for n, t in [
                ("symbol", "STRING"), ("name", "STRING"), ("sector", "STRING"),
                ("last", "DOUBLE"), (col, "DOUBLE"), ("market_cap", "DOUBLE")]],
            rows=rows, row_count=len(rows)), False
    return run_query("heatmap", {"metric_col": col}, identity)


def get_events(symbol: str, identity: Identity) -> tuple[list[dict], bool]:
    if get_settings().mock:
        df = synthetic.corp_events(symbol)
        return df.to_dict("records"), False
    rs, hit = run_query("events", {"symbol": symbol}, identity)
    return [{c.name: r[i] for i, c in enumerate(rs.columns)} for r in rs.rows], hit


def get_watchlists(identity: Identity) -> list[dict]:
    """Default watchlist groups — user lists persist via Delta/localStorage later."""
    return [
        {"id": "stocks", "name": "Stocks", "symbols": ["NVDA", "AAPL", "MSFT", "AMD", "AMZN", "META", 
            "LLY", "JPM"]},
        {"id": "etfs", "name": "ETFs", "symbols": ["SPY", "QQQ", "IWM", "XLF", "XLE", "GLD", "TLT"]},
        {"id": "futures-fx", "name": "Futures / FX", "symbols": ["ES=F", "CL=F", "EURUSD=X", "JPY=X"]},
        {"id": "crypto", "name": "Crypto", "symbols": ["BTC-USD", "ETH-USD"]},
    ]


def _df_result(df: pd.DataFrame) -> ResultSet:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.date.astype(str)
    cols = [Column(name=c, type="STRING" if df[c].dtype == object else str(df[c].dtype).upper())
            for c in df.columns]
    return ResultSet(columns=cols, rows=df.astype(object).values.tolist(), row_count=len(df))
