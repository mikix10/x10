from __future__ import annotations

from x10_api import hello


def test_hello_reports_readiness():
    assert hello() == "X10 API ready"
