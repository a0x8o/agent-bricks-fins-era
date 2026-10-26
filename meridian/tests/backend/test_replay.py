"""Bar Replay point-in-time correctness — nothing after `until` may leak."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _bars(symbol="NVDA", rng="5Y", until=None):
    q = f"?range={rng}&interval=1D" + (f"&until={until}" if until else "")
    r = client.get(f"/api/prices/{symbol}{q}")
    r.raise_for_status()
    return r.json()["bars"]


def test_until_clamps_bars():
    full = _bars()
    cutoff = full[len(full) // 2]["time"]
    clipped = _bars(until=cutoff)
    assert clipped[-1]["time"] <= cutoff
    assert len(clipped) < len(full)
    assert all(b["time"] <= cutoff for b in clipped)


def test_until_quote_has_no_future_data():
    full = _bars()
    cutoff = full[len(full) // 2]["time"]
    q_now = client.get("/api/quote/NVDA").json()
    q_past = client.get(f"/api/quote/NVDA?until={cutoff}").json()
    assert q_past["as_of"] <= cutoff
    # performance numbers computed on truncated data must differ
    assert q_past["last"] != q_now["last"] or q_past["perf"]["ytd"] != q_now["perf"]["ytd"]


def test_until_none_matches_full():
    assert len(_bars()) == len(_bars(until=None))


def test_indicators_clamp():
    cutoff = _bars()[len(_bars()) // 2]["time"]
    full = client.get("/api/indicators/NVDA?type=sma&params={\"length\":20}&range=5Y").json()["points"]
    cut = client.get(f"/api/indicators/NVDA?type=sma&params={{\"length\":20}}&range=5Y&until={cutoff}").json()["points"]
    assert len(cut) <= len(full)
    assert max(p["time"] for p in cut) <= cutoff


def test_replay_step_reveal_is_prefix():
    """Client reveals bars by stepping an index over the prefetched array;
    server guarantees the array is already clamped — assert prefix property."""
    full = _bars()
    cutoff = full[len(full) - 100]["time"]
    times = [b["time"] for b in _bars(until=cutoff)]
    assert times == sorted(times)
    for i in range(0, len(times), 10):
        assert all(t <= times[i] for t in times[: i + 1])  # every revealed prefix ≤ cursor
