"""Known-answer scaffold.

This test is intentionally skipped for now. It documents the next step: run a
small frozen EUR/USD sample through the engine and assert an exact trade ledger.
"""

import pytest


@pytest.mark.skip(reason="Known-answer fixture and full backtest loop not implemented in v0.1")
def test_known_answer_eurusd_rsi_run() -> None:
    expected = {
        "trade_count": 3,
        "ending_equity": 10_184.25,
        "first_trade_id": "eurusd-rsi-0001",
    }
    assert expected["trade_count"] == 3
