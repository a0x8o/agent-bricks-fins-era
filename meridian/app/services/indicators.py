"""Technical indicators — pure pandas/numpy functions.

Each returns a DataFrame aligned on the input index with named output columns.
Reference values for unit tests live in tests/backend/test_indicators.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, length: int = 20) -> pd.Series:
    return close.rolling(length, min_periods=length).mean()


def ema(close: pd.Series, length: int = 20) -> pd.Series:
    return close.ewm(span=length, adjust=False, min_periods=length).mean()


def dema(close: pd.Series, length: int = 20) -> pd.Series:
    e1 = ema(close, length)
    e2 = e1.ewm(span=length, adjust=False).mean()
    return 2 * e1 - e2


def hma(close: pd.Series, length: int = 20) -> pd.Series:
    """Hull MA: WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    half = max(int(length / 2), 1)
    sqrt_n = max(int(np.sqrt(length)), 1)
    wma_half = _wma(close, half)
    wma_full = _wma(close, length)
    return _wma(2 * wma_half - wma_full, sqrt_n)


def _wma(s: pd.Series, length: int) -> pd.Series:
    w = np.arange(1, length + 1, dtype=float)
    return s.rolling(length, min_periods=length).apply(lambda x: float((x * w).sum() / w.sum()), raw=True)


def bollinger(close: pd.Series, length: int = 20, mult: float = 2.0) -> pd.DataFrame:
    mid = sma(close, length)
    sd = close.rolling(length, min_periods=length).std(ddof=0)
    return pd.DataFrame({"basis": mid, "upper": mid + mult * sd, "lower": mid - mult * sd})


def envelope(close: pd.Series, length: int = 20, pct: float = 0.05) -> pd.DataFrame:
    mid = sma(close, length)
    return pd.DataFrame({"basis": mid, "upper": mid * (1 + pct), "lower": mid * (1 - pct)})


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    tp = (high + low + close) / 3
    pv = tp * volume
    return pv.cumsum() / volume.cumsum()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's RSI (smoothed gains/losses)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    return out.mask(avg_loss == 0, 100.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ef = close.ewm(span=fast, adjust=False).mean()
    es = close.ewm(span=slow, adjust=False).mean()
    line = ef - es
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def aroon(high: pd.Series, low: pd.Series, length: int = 25) -> pd.DataFrame:
    """Aroon up/down — position of the most recent extreme within the window, as %."""
    n = len(high)
    up = np.full(n, np.nan)
    dn = np.full(n, np.nan)
    hv, lv = high.to_numpy(), low.to_numpy()
    for i in range(length - 1, n):
        w_h = hv[i - length + 1 : i + 1]
        w_l = lv[i - length + 1 : i + 1]
        up[i] = (np.argmax(w_h) / (length - 1)) * 100
        dn[i] = (np.argmin(w_l) / (length - 1)) * 100
    return pd.DataFrame({"aroon_up": up, "aroon_down": dn}, index=high.index)


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3) -> pd.DataFrame:
    ll = low.rolling(k, min_periods=k).min()
    hh = high.rolling(k, min_periods=k).max()
    pct_k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    pct_d = pct_k.rolling(d, min_periods=d).mean()
    return pd.DataFrame({"stoch_k": pct_k, "stoch_d": pct_d})


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def klinger(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
            fast: int = 34, slow: int = 55, signal: int = 13) -> pd.DataFrame:
    """Klinger Oscillator — volume-force EMA spread."""
    tp = (high + low + close)
    trend = (tp.diff() > 0).astype(float) * 2 - 1  # +1 rising, -1 falling
    dm = (high - low).diff().abs()
    # measurement accumulates within same-trend runs
    cm_vals = np.zeros(len(tp))
    run = 0.0
    prev_trend = 0.0
    for i in range(1, len(tp)):
        if trend.iloc[i] == prev_trend:
            run += dm.iloc[i]
        else:
            run = dm.iloc[i]
        cm_vals[i] = run if run else dm.iloc[i]
        prev_trend = trend.iloc[i]
    vf = volume * trend * (dm / pd.Series(cm_vals, index=tp.index).replace(0, np.nan)).abs() * 100
    kvo = vf.ewm(span=fast, adjust=False).mean() - vf.ewm(span=slow, adjust=False).mean()
    sig = kvo.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"kvo": kvo.fillna(0), "kvo_signal": sig.fillna(0)})


def ma_ribbon(close: pd.Series, base: int = 10, step: int = 5, count: int = 10) -> pd.DataFrame:
    """count EMAs at base, base+step, ... — rendered as a gradient ribbon."""
    return pd.DataFrame({f"ma{base + i * step}": ema(close, base + i * step) for i in range(count)})


REGISTRY = {
    "sma": lambda df, p: pd.DataFrame({"sma": sma(df["close"], int(p.get("length", 20)))}),
    "ema": lambda df, p: pd.DataFrame({"ema": ema(df["close"], int(p.get("length", 20)))}),
    "dema": lambda df, p: pd.DataFrame({"dema": dema(df["close"], int(p.get("length", 20)))}),
    "hma": lambda df, p: pd.DataFrame({"hma": hma(df["close"], int(p.get("length", 20)))}),
    "bollinger": lambda df, p: bollinger(df["close"], int(p.get("length", 20)), float(p.get("mult", 2.0))),
    "envelope": lambda df, p: envelope(df["close"], int(p.get("length", 20)), float(p.get("pct", 0.05))),
    "vwap": lambda df, p: pd.DataFrame({"vwap": vwap(df["high"], df["low"], df["close"], df["volume"])}),
    "rsi": lambda df, p: pd.DataFrame({"rsi": rsi(df["close"], int(p.get("length", 14)))}),
    "macd": lambda df, p: macd(df["close"], int(p.get("fast", 12)), int(p.get("slow", 26)), 
        int(p.get("signal", 9))),
    "aroon": lambda df, p: aroon(df["high"], df["low"], int(p.get("length", 25))),
    "stochastic": lambda df, p: stochastic(df["high"], df["low"], df["close"], int(p.get("k", 14)), 
        int(p.get("d", 3))),
    "atr": lambda df, p: pd.DataFrame({"atr": atr(df["high"], df["low"], df["close"], int(p.get("length",
        14)))}),
    "klinger": lambda df, p: klinger(df["high"], df["low"], df["close"], df["volume"]),
    "ribbon": lambda df, p: ma_ribbon(df["close"], int(p.get("base", 10)), int(p.get("step", 5)), 
        int(p.get("count", 10))),
}

OSCILLATORS = {"rsi", "macd", "aroon", "stochastic", "atr", "klinger"}
OVERLAYS = {"sma", "ema", "dema", "hma", "bollinger", "envelope", "vwap", "ribbon"}
