from __future__ import annotations

import pytest

from x10_connectors import BaseConnector, ConnectorResult


class _StubConnector(BaseConnector):
    def fetch(self) -> ConnectorResult:
        return ConnectorResult(source=self.source_name, status="ok")


def test_base_connector_requires_a_fetch_implementation():
    with pytest.raises(NotImplementedError):
        BaseConnector("ecmwf-ifs-oper").fetch()


def test_subclass_reports_its_source():
    result = _StubConnector("ecmwf-ifs-oper").fetch()
    assert result == ConnectorResult(source="ecmwf-ifs-oper", status="ok", message="")
