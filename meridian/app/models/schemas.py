"""Pydantic v2 response models — single OpenAPI contract."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    error: ApiError


class Column(BaseModel):
    name: str
    type: str


class ResultSet(BaseModel):
    columns: list[Column]
    rows: list[list[Any]]
    row_count: int
    truncated: bool = False


class Bar(BaseModel):
    time: str  # YYYY-MM-DD (daily) or ISO ts (intraday)
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int


class PricesResponse(BaseModel):
    symbol: str
    interval: str
    bars: list[Bar]
    as_of: str | None = None
    adjusted: bool = True


class IndicatorPoint(BaseModel):
    time: str
    value: float | None = None
    extra: dict[str, float | None] = Field(default_factory=dict)


class IndicatorResponse(BaseModel):
    symbol: str
    type: str
    params: dict[str, Any]
    points: list[IndicatorPoint]


class SecurityOut(BaseModel):
    symbol: str
    name: str
    asset_class: str
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    currency: str = "USD"
    market_cap: float | None = None


class PerfGrid(BaseModel):
    w1: float | None = None
    m1: float | None = None
    m3: float | None = None
    m6: float | None = None
    ytd: float | None = None
    y1: float | None = None


class TechnicalsSummary(BaseModel):
    score: float  # -1..1
    label: Literal["strong_sell", "sell", "neutral", "buy", "strong_buy"]


class QuoteResponse(BaseModel):
    symbol: str
    name: str
    last: float
    change: float
    change_pct: float
    currency: str = "USD"
    market_status: Literal["open", "closed", "pre", "post"] = "closed"
    perf: PerfGrid
    technicals: TechnicalsSummary
    news_headline: str | None = None
    as_of: str


class ChartSpec(BaseModel):
    """Ranked chart suggestion for a Genie result."""

    kind: Literal[
        "kpi", "line", "area", "candlestick", "multi_line", "bar", "bar_h",
        "donut", "treemap", "scatter", "table"
    ]
    score: int
    x: str | None = None
    y: list[str] = Field(default_factory=list)
    series: str | None = None
    normalized: bool = False
    reason: str = ""


class GenieAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    context_symbol: str | None = None
    as_of: str | None = None  # replay cursor date; appended as instruction


class GenieMessageOut(BaseModel):
    conversation_id: str
    message_id: str
    status: str
    text: str | None = None
    sql: str | None = None
    query_description: str | None = None
    result: ResultSet | None = None
    suggested: list[str] = Field(default_factory=list)
    attachment_id: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    as_of: str | None = None
    lookahead_warning: bool = False


class WatchlistOut(BaseModel):
    id: str
    name: str
    symbols: list[str]
