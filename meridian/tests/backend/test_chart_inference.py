"""Chart inference rule coverage — every rule in the spec."""

from app.models.schemas import Column
from app.services.chart_inference import infer


def cols(*specs):
    return [Column(name=n, type=t) for n, t in specs]


def test_date_plus_numeric_is_line():
    specs = infer(cols(("d", "DATE"), ("v", "DOUBLE")), [["2024-01-01", 1.0], ["2024-01-02", 2.0]])
    assert specs[0].kind == "line"
    assert specs[0].score > specs[1].score


def test_ohlc_is_candlestick():
    specs = infer(cols(("d", "DATE"), ("open", "DOUBLE"), ("high", "DOUBLE"), ("low", "DOUBLE"), ("close", "DOUBLE")),
                  [["2024-01-01", 1, 2, 0.5, 1.5]])
    assert specs[0].kind == "candlestick"


def test_date_multi_numeric_is_multiline_with_normalized_alt():
    specs = infer(cols(("d", "DATE"), ("a", "DOUBLE"), ("b", "DOUBLE")),
                  [["2024-01-01", 1, 2]])
    kinds = {s.kind: s for s in specs}
    assert "multi_line" in kinds
    assert any(s.normalized for s in specs)


def test_categorical_few_is_bar_many_is_horizontal():
    few = infer(cols(("sec", "STRING"), ("v", "DOUBLE")), [["A", 1], ["B", 2]])
    assert any(s.kind == "bar" for s in few)
    many = infer(cols(("sec", "STRING"), ("v", "DOUBLE")), [[f"S{i}", i] for i in range(12)])
    assert many[0].kind == "bar_h"


def test_share_column_is_donut():
    specs = infer(cols(("sec", "STRING"), ("weight_pct", "DOUBLE")), [["Tech", 60], ["Fin", 40]])
    assert specs[0].kind == "donut"


def test_two_numerics_is_scatter():
    specs = infer(cols(("pe", "DOUBLE"), ("ret", "DOUBLE")), [[10, 5], [20, 9]])
    assert specs[0].kind == "scatter"


def test_single_value_is_kpi():
    specs = infer(cols(("total", "BIGINT")), [[42]])
    assert specs[0].kind == "kpi" and specs[0].score == 100


def test_fallback_is_table():
    specs = infer(cols(("a", "STRING"), ("b", "STRING")), [["x", "y"]])
    assert specs[-1].kind == "table"
