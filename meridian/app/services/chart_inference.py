"""Chart inference: result schema + sample rows → ranked chart specs.

Rules are order-scored so tests can assert each independently.
"""

from __future__ import annotations

from typing import Any

from ..models.schemas import ChartSpec, Column

_DATE_TYPES = {"DATE", "TIMESTAMP", "TIMESTAMP_NTZ", "TIMESTAMP_LTZ"}
_NUM_TYPES = {"INT", "BIGINT", "SMALLINT", "TINYINT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL", "LONG"}
_OHLC = {"open", "high", "low", "close"}


def _is_date(t: str) -> bool:
    t = t.upper()
    return any(k in t for k in ("DATE", "TIMESTAMP", "TIME"))


def _is_num(t: str) -> bool:
    t = t.upper()
    return any(k in t for k in _NUM_TYPES) or t.startswith("DECIMAL")


def infer(columns: list[Column], rows: list[list[Any]]) -> list[ChartSpec]:
    specs: list[ChartSpec] = []
    names = [c.name.lower() for c in columns]

    if not columns:
        return [ChartSpec(kind="table", score=0, reason="no columns")]

    if len(rows) == 1 and len(columns) >= 1 and _is_num(columns[0].type):
        if len(columns) == 1:
            return [ChartSpec(kind="kpi", score=100, y=[columns[0].name], reason="single value")]

    date_i = next((i for i, c in enumerate(columns) if _is_date(c.type)), None)
    num_i = [i for i, c in enumerate(columns) if _is_num(c.type)]
    cat_i = [i for i, c in enumerate(columns) if not _is_date(c.type) and not _is_num(c.type)]

    if date_i is not None:
        dname = columns[date_i].name
        if _OHLC.issubset(set(names)):
            specs.append(ChartSpec(kind="candlestick", score=95, x=dname,
                                   y=[columns[names.index("open")].name, columns[names.index("high")].name,
                                      columns[names.index("low")].name, columns[names.index("close")].name],
                                   reason="date + OHLC"))
        if len(num_i) == 1:
            specs.append(ChartSpec(kind="line", score=90, x=dname, y=[columns[num_i[0]].name], 
                reason="date + 1 numeric"))
            specs.append(ChartSpec(kind="area", score=80, x=dname, y=[columns[num_i[0]].name], 
                reason="date + 1 numeric (alt)"))
        elif len(num_i) > 1:
            y = [columns[i].name for i in num_i[:6]]
            specs.append(ChartSpec(kind="multi_line", score=88, x=dname, y=y,
                                   reason="date + several numerics"))
            specs.append(ChartSpec(kind="multi_line", score=78, x=dname, y=y, normalized=True,
                                   reason="rebased to 100 for comparability"))
        return specs or [ChartSpec(kind="table", score=0, reason="date but no numeric")]

    if cat_i and num_i:
        cname = columns[cat_i[0]].name
        nname = columns[num_i[0]].name
        n_cat = len({r[cat_i[0]] for r in rows})
        # part-of-whole heuristic: column name hints or fractions
        if any(k in columns[num_i[0]].name.lower() for k in ("pct", "share", "weight", "percent")):
            specs.append(ChartSpec(kind="donut", score=85, x=cname, y=[nname], reason="categorical share"))
            specs.append(ChartSpec(kind="treemap", score=70, x=cname, y=[nname],
                                   reason="categorical share (alt)"))
        if n_cat > 8:
            specs.append(ChartSpec(kind="bar_h", score=85, x=cname, y=[nname],
                                   reason=">8 categories → horizontal"))
        else:
            specs.append(ChartSpec(kind="bar", score=82, x=cname, y=[nname], reason="categorical + numeric"))
        return specs

    if len(num_i) >= 2:
        specs.append(ChartSpec(kind="scatter", score=80, x=columns[num_i[0]].name,
                               y=[columns[num_i[1]].name],
                               series=columns[num_i[2]].name if len(num_i) > 2 else None,
                               reason="2 numerics → scatter"))

    return specs or [ChartSpec(kind="table", score=0, reason="no chartable shape")]
