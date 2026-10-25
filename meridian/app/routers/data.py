from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..auth import resolve_identity
from ..config import get_settings
from ..models.schemas import (
    IndicatorPoint,
    IndicatorResponse,
    PerfGrid,
    PricesResponse,
    QuoteResponse,
    ResultSet,
    SecurityOut,
    TechnicalsSummary,
    WatchlistOut,
)
from ..services import indicators as ind
from ..services import market_data as md
from ..services import synthetic

router = APIRouter(tags=["data"])


def _cache_headers(resp: Response, hit: bool) -> None:
    resp.headers["X-Cache"] = "HIT" if hit else "MISS"


@router.get("/api/securities", response_model=list[SecurityOut])
def securities(request: Request, response: Response, query: str = "") -> list[SecurityOut]:
    out, hit = md.search_securities(query, resolve_identity(request))
    _cache_headers(response, hit)
    return out


@router.get("/api/prices/{symbol}", response_model=PricesResponse)
def prices(request: Request, response: Response, symbol: str,
           interval: str = "1D", range: str = "1Y", until: str | None = None) -> PricesResponse:
    bars, as_of, hit = md.get_bars(symbol.upper(), range, interval, until, resolve_identity(request))
    _cache_headers(response, hit)
    return PricesResponse(symbol=symbol.upper(), interval=interval, bars=bars, as_of=as_of)


@router.get("/api/indicators/{symbol}", response_model=IndicatorResponse)
def indicator(request: Request, symbol: str, type: str = "ema",
              range: str = "1Y", until: str | None = None,
              params: str | None = None) -> IndicatorResponse:
    import json

    p = json.loads(params) if params else {}
    fn = ind.REGISTRY.get(type)
    if fn is None:
        raise ValueError(f"unknown indicator '{type}'; allowed: {sorted(ind.REGISTRY)}")
    symbol = symbol.upper()
    if get_settings().mock:
        df = synthetic.price_window(symbol, md._range_start(range),
                                    __import__("pandas").Timestamp(until) if until else None)
    else:
        bars, _, _ = md.get_bars(symbol, range, "1D", until, resolve_identity(request))
        import pandas as pd

        df = pd.DataFrame([b.model_dump() for b in bars])
        df["trade_date"] = pd.to_datetime(df["time"])
        df["volume"] = df["volume"].astype("int64")
    out = fn(df.set_index("trade_date").reset_index(), p)
    out.index = df["trade_date"]
    points = [
        IndicatorPoint(time=t.date().isoformat(), **{
            "value": None,
            "extra": {c: (None if r[c] != r[c] else float(r[c])) for c in out.columns},
        })
        for t, r in zip(out.index, out.to_dict("records"), strict=False)
    ]
    # collapse single-output indicators to `value`
    if len(out.columns) == 1:
        col = out.columns[0]
        points = [IndicatorPoint(time=pt.time, value=pt.extra.get(col)) for pt in points]
    return IndicatorResponse(symbol=symbol, type=type, params=p, points=points)


def _technicals(df) -> TechnicalsSummary:
    """Score -1..1 from indicator signals: price vs SMAs, RSI zone, MACD hist."""
    import numpy as np

    close = df["close"]
    votes: list[float] = []
    for n in (20, 50, 200):
        m = ind.sma(close, n).iloc[-1]
        if m == m:
            votes.append(1.0 if close.iloc[-1] > m else -1.0)
    r = ind.rsi(close).iloc[-1]
    if r == r:
        votes.append(1.0 if r > 60 else (-1.0 if r < 40 else 0.0))
    h = ind.macd(close)["hist"].iloc[-1]
    if h == h:
        votes.append(float(np.sign(h)))
    score = float(np.mean(votes)) if votes else 0.0
    label = ("strong_buy" if score > 0.5 else "buy" if score > 0.15 else
             "strong_sell" if score < -0.5 else "sell" if score < -0.15 else "neutral")
    return TechnicalsSummary(score=round(score, 2), label=label)


@router.get("/api/quote/{symbol}", response_model=QuoteResponse)
def quote(request: Request, response: Response, symbol: str, until: str | None = None) -> QuoteResponse:
    symbol = symbol.upper()
    identity = resolve_identity(request)
    vals, hit = md.get_quote(symbol, identity, until)
    _cache_headers(response, hit)
    tech = None
    if get_settings().mock:
        import pandas as pd

        df = synthetic.prices(symbol)
        if until:
            df = df[df.trade_date <= pd.Timestamp(until)]
        tech = _technicals(df)
    else:
        bars, _, _ = md.get_bars(symbol, "1Y", "1D", None, identity)
        if bars:
            import pandas as pd

            df = pd.DataFrame([b.model_dump() for b in bars])
            tech = _technicals(df)
    tech = tech or TechnicalsSummary(score=0.0, label="neutral")
    news = None
    try:
        evts, _ = md.get_events(symbol, identity)
        news = next((e["detail"] for e in reversed(evts)), None)
    except Exception:
        pass
    return QuoteResponse(
        symbol=symbol, name=vals.get("name", symbol), last=float(vals.get("last", 0)),
        change=float(vals.get("change", 0)), change_pct=float(vals.get("change_pct", 0)),
        currency=vals.get("currency", "USD"), market_status="closed",
        perf=PerfGrid(w1=vals.get("ret_1w") or vals.get("perf", {}).get("w1"),
                      m1=vals.get("ret_1m"), m3=vals.get("ret_3m"), m6=vals.get("ret_6m"),
                      ytd=vals.get("ret_ytd") or vals.get("perf", {}).get("ytd"),
                      y1=vals.get("ret_1y")),
        technicals=tech, news_headline=news, as_of=str(vals.get("as_of", "")),
    )


@router.get("/api/events/{symbol}")
def events(request: Request, symbol: str) -> list[dict]:
    evts, _ = md.get_events(symbol.upper(), resolve_identity(request))
    return evts


@router.get("/api/screener", response_model=ResultSet)
def screener(request: Request, response: Response, sector: str | None = None) -> ResultSet:
    rs, hit = md.get_screener(sector, resolve_identity(request))
    _cache_headers(response, hit)
    return rs


@router.get("/api/heatmap", response_model=ResultSet)
def heatmap(request: Request, response: Response, universe: str = "all", metric: str = "1m") -> ResultSet:
    rs, hit = md.get_heatmap(metric, resolve_identity(request))
    _cache_headers(response, hit)
    return rs


@router.get("/api/fundamentals/{symbol}", response_model=ResultSet)
def fundamentals(request: Request, symbol: str) -> ResultSet:
    rs, _ = md.get_fundamentals(symbol.upper(), resolve_identity(request))
    return rs


@router.get("/api/portfolio/{portfolio_id}", response_model=ResultSet)
def portfolio(request: Request, portfolio_id: str) -> ResultSet:
    rs, _ = md.get_portfolio(portfolio_id, resolve_identity(request))
    return rs


@router.get("/api/watchlists", response_model=list[WatchlistOut])
def watchlists(request: Request) -> list[WatchlistOut]:
    return [WatchlistOut(**w) for w in md.get_watchlists(resolve_identity(request))]


@router.put("/api/watchlists/{list_id}", response_model=WatchlistOut)
def put_watchlist(request: Request, list_id: str, body: WatchlistOut) -> WatchlistOut:
    # v1: persistence flag off → client keeps it in localStorage; endpoint validates shape.
    body.id = list_id
    return body
