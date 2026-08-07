"""Unit tests for the `_instrumented_ui_op` decorator and the pure-data
callback contracts (no NiceGUI context needed - `callbacks.py` is
deliberately UI-framework-free, see its module docstring)."""
from __future__ import annotations

import pytest

from app.ui.callbacks import _instrumented_ui_op


async def test_decorated_function_returns_value():
    @_instrumented_ui_op("probe")
    async def fn(x):
        return x * 2

    assert await fn(21) == 42


async def test_decorated_function_propagates_exceptions():
    @_instrumented_ui_op("probe_error")
    async def fn():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await fn()


async def test_decorated_function_records_metrics():
    from app.observability.metrics import ui_operations_total

    @_instrumented_ui_op("probe_metrics")
    async def fn():
        return "ok"

    before = ui_operations_total.labels(operation="probe_metrics", status="success")._value.get()
    await fn()
    after = ui_operations_total.labels(operation="probe_metrics", status="success")._value.get()
    assert after == before + 1
