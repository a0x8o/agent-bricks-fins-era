"""Indicator math vs hand-computed reference values."""

import numpy as np
import pandas as pd
import pytest

from app.services import indicators as ind

C = pd.Series


def test_sma_reference():
    s = C([1, 2, 3, 4, 5], dtype=float)
    out = ind.sma(s, 3)
    assert out.isna().iloc[:2].all()
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_first_value():
    s = C([10.0] * 30)
    out = ind.ema(s, 10)
    assert out.iloc[-1] == pytest.approx(10.0)


def test_rsi_bounds_and_extremes():
    up = C(np.linspace(1, 100, 60))
    assert ind.rsi(up, 14).iloc[-1] > 95
    down = C(np.linspace(100, 1, 60))
    assert ind.rsi(down, 14).iloc[-1] < 5


def test_bollinger_band_width():
    rng = np.random.default_rng(0)
    s = C(rng.normal(100, 2, 100))
    b = ind.bollinger(s, 20, 2.0)
    row = b.iloc[-1]
    assert row["upper"] > row["basis"] > row["lower"]
    assert (row["upper"] - row["basis"]) == pytest.approx(row["basis"] - row["lower"])


def test_macd_hist_is_line_minus_signal():
    s = C(np.sin(np.linspace(0, 8, 200)) * 10 + 100)
    m = ind.macd(s)
    assert m["hist"].iloc[-1] == pytest.approx(m["macd"].iloc[-1] - m["signal"].iloc[-1])


def test_atr_positive():
    df = pd.DataFrame({"high": [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
                       "low": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24],
                       "close": [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]})
    assert ind.atr(df["high"], df["low"], df["close"], 14).iloc[-1] > 0


def test_aroon_extreme_placement():
    high = C(list(range(30)))
    low = C(list(range(30)))
    a = ind.aroon(high, low, 25)
    # most recent bar is both highest high and lowest low position index
    assert a["aroon_up"].iloc[-1] == pytest.approx(100.0)


def test_stochastic_bounds():
    n = 60
    df = pd.DataFrame({"high": C(np.linspace(1, 100, n) + 2),
                       "low": C(np.linspace(1, 100, n) - 2),
                       "close": C(np.linspace(1, 100, n))})
    st = ind.stochastic(df["high"], df["low"], df["close"])
    v = st["stoch_k"].dropna()
    assert ((v >= 0) & (v <= 100)).all()


def test_ribbon_count():
    s = C(np.linspace(50, 150, 400))
    r = ind.ma_ribbon(s, base=10, step=5, count=10)
    assert len(r.columns) == 10
    # longer MAs are smoother in an uptrend → last value ordering
    assert r.iloc[-1]["ma10"] > r.iloc[-1]["ma55"]
