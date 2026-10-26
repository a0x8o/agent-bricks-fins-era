#!/usr/bin/env python3
"""Genie evaluation harness — 25 benchmark questions against the live space.

Usage:
    DATABRICKS_CONFIG_PROFILE=DEFAULT python tests/genie_eval/run_eval.py

Writes docs/GENIE_EVAL.md. Target: >=85% pass. Each check verifies the message
completes, returns SQL or a declared narrative-only answer, and (where
specified) row-count / required-column expectations.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

SPACE_ID = os.getenv("GENIE_SPACE_ID", "01f1d07ccf61185bbcc0f5cda95441c6")
WAREHOUSE = os.getenv("DATABRICKS_WAREHOUSE_ID", "00a19186c27fa1de")
PROFILE = os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
TIMEOUT_S = 150

# (question, min_rows, required_columns or None)
BENCH: list[tuple[str, int, list[str] | None]] = [
    ("What was NVDA's 1-year return?", 1, ["ret_1y"]),
    ("Top 10 stocks by 1-month return", 5, ["ret_1m"]),
    ("Compare AAPL and MSFT year-to-date return", 2, ["symbol"]),
    ("Which sectors drove the demo portfolio's value?", 1, None),
    ("Show AAPL quarterly revenue over the last 3 years", 4, ["revenue"]),
    ("Semiconductor names ranked by free cash flow yield", 1, None),
    ("Daily closes for TSLA over the last month", 10, ["close"]),
    ("What are the demo portfolio weights by symbol?", 5, None),
    ("Largest healthcare companies by market cap", 1, ["market_cap"]),
    ("Did NVDA beat SPY over the last 6 months?", 1, None),
    ("Average 1-year return by sector", 3, None),
    ("Which portfolio positions have negative unrealized P&L?", 0, None),
    ("Show LLY quarterly EPS trend", 4, None),
    ("Highest 1-year return among technology stocks", 1, None),
    ("What is the total market value of the demo portfolio?", 1, None),
    ("Stocks with 6-month return above 20 percent", 0, None),
    ("XOM and energy sector YTD performance", 1, None),
    ("Monthly closes for QQQ over the last year", 6, None),
    ("How many securities are in each asset class?", 2, None),
    ("Largest single-day gain for TSLA this year", 0, None),
    ("MSFT revenue and net income last 4 quarters", 4, None),
    ("Which sector has the best YTD return on average?", 1, None),
    ("Show BTC-USD daily close for the last 3 months", 30, None),
    ("Companies with FCF yield above 3 percent", 0, None),
    ("Portfolio P&L by position", 5, None),
]


def token() -> tuple[str, dict[str, str]]:
    out = subprocess.run(["databricks", "auth", "token", "--profile", PROFILE],
                         capture_output=True, text=True, check=True)
    tok = json.loads(out.stdout)
    desc = subprocess.run(["databricks", "auth", "describe", "--profile", PROFILE, "-o", "json"],
                          capture_output=True, text=True, check=True)
    host = json.loads(desc.stdout)["details"]["host"].rstrip("/")
    return host, {"Authorization": f"Bearer {tok['access_token']}", "Content-Type": "application/json"}


def ask(host: str, h: dict, question: str) -> dict:
    r = httpx.post(f"{host}/api/2.0/genie/spaces/{SPACE_ID}/start-conversation",
                   headers=h, json={"content": question}, timeout=30)
    r.raise_for_status()
    d = r.json()
    cid = d.get("conversation_id") or d.get("message", {}).get("conversation_id")
    mid = d.get("message_id") or d.get("message", {}).get("id")
    t0 = time.time()
    while time.time() - t0 < TIMEOUT_S:
        time.sleep(3)
        m = httpx.get(f"{host}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{cid}/messages/{mid}",
                      headers=h, timeout=30).json()
        if m.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
    atts = m.get("attachments") or []
    sql = next((a["query"].get("query") for a in atts if "query" in a), None)
    aid = next((a.get("attachment_id") for a in atts if "query" in a), None)
    text = " ".join(a["text"].get("content", "") for a in atts if "text" in a)
    rows, cols = [], []
    if aid and m.get("status") == "COMPLETED":
        res = httpx.get(
            f"{host}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{cid}/messages/{mid}/attachments/{aid}/query-result",
            headers=h, timeout=60)
        if res.status_code == 200:
            rd = res.json()
            meta = rd.get("statement_response", {})
            cols = [c.get("name") for c in (meta.get("manifest", {}).get("schema", {}).get("columns") or [])]
            rows = (meta.get("result", {}).get("data_array") or rd.get("data_array") or [])
    return {"status": m.get("status"), "sql": sql, "text": text, "cols": cols,
            "rows": len(rows), "latency": round(time.time() - t0, 1)}


def main() -> None:
    host, h = token()
    results = []
    passed = 0
    for i, (q, min_rows, req_cols) in enumerate(BENCH, 1):
        try:
            r = ask(host, h, q)
            ok = r["status"] == "COMPLETED" and r["rows"] >= min_rows
            if req_cols:
                ok = ok and all(any(rc.lower() == c.lower() for rc in r["cols"]) for c in req_cols)
            ok = ok and bool(r["sql"] or r["text"])
            note = ""
        except Exception as e:  # noqa: BLE001
            r = {"status": "ERROR", "sql": None, "rows": 0, "cols": [], "latency": 0}
            ok, note = False, str(e)[:100]
        passed += ok
        results.append((i, q, r, ok, note))
        print(f"[{i:02d}/25] {'PASS' if ok else 'FAIL'} {r['status']:<10} rows={r['rows']:<4} {q[:60]}", flush=True)

    pct = passed / len(BENCH) * 100
    out = Path(__file__).resolve().parent.parent.parent / "docs" / "GENIE_EVAL.md"
    lines = ["# Genie evaluation scorecard", "",
             f"Space: `{SPACE_ID}` · run against live workspace · target ≥85%", "",
             f"**Score: {passed}/{len(BENCH)} = {pct:.0f}%**", "",
             "| # | Question | Status | Rows | SQL? | Result |", "|---|---|---|---|---|---|"]
    for i, q, r, ok, note in results:
        lines.append(f"| {i} | {q[:60]} | {r['status']} | {r['rows']} | {'yes' if r['sql'] else 'no'} | {'PASS' if ok else 'FAIL' + (' — ' + note if note else '')} |")
    lines += ["", "## Failures and suggested Genie-space fixes", ""]
    for i, q, r, ok, note in results:
        if not ok:
            lines.append(f"- **Q{i}** ({q[:60]}): status={r['status']} — consider adding an example Q/SQL pair or instruction clarifying this pattern.")
    out.write_text("\n".join(lines) + "\n")
    print(f"\nScore: {passed}/{len(BENCH)} = {pct:.0f}% → {out}")


if __name__ == "__main__":
    main()
