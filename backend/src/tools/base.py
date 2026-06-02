"""Shared tool result types."""

from typing import Any, TypedDict


class ToolResult(TypedDict):
    """Normalized result returned by domain tools."""

    ok: bool
    data: dict[str, Any]
    error: str | None
    trace: dict[str, Any]


def tool_result(
    *,
    ok: bool,
    data: dict[str, Any] | None = None,
    error: str | None = None,
    trace: dict[str, Any] | None = None,
) -> ToolResult:
    """Build a consistent tool result payload."""
    return {
        "ok": ok,
        "data": data or {},
        "error": error,
        "trace": trace or {},
    }
