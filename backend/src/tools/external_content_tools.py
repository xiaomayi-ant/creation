"""External content enrichment tools for script generation.

These tools intentionally start as provider-neutral placeholders. They expose
stable function-calling schemas now, while leaving room to wire real Web/Douyin
providers later without changing graph nodes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.core.config import Settings, settings
from src.core.logger import get_logger
from src.tools.base import ToolResult, tool_result

logger = get_logger(__name__)


class WebSearchInput(BaseModel):
    """Function-calling schema for external web search."""

    query: str = Field(..., description="Search query derived from the user request.")
    topic: str = Field(default="", description="Optional normalized topic.")
    target_audience: str = Field(default="", description="Optional audience hint.")
    max_results: int = Field(default=5, ge=1, le=10)


class DouyinTrendInput(BaseModel):
    """Function-calling schema for Douyin trend lookup."""

    keyword: str = Field(default="", description="Keyword used to filter trend items.")
    category: str = Field(default="hot", description="Trend category, e.g. hot/drama/life.")
    limit: int = Field(default=10, ge=1, le=30)
    region: str = Field(default="CN")


class WebSearchTool:
    """Retrieve web context when internal RAG coverage is insufficient."""

    name = "web_search_external_context"
    description = (
        "Search the public web for recent background context, real-world signals, "
        "and creative references for short-drama script planning."
    )

    def __init__(self, config: Settings | None = None):
        self.config = config or settings

    def run(
        self,
        *,
        query: str,
        topic: str = "",
        target_audience: str = "",
        max_results: int = 5,
    ) -> ToolResult:
        """Return normalized web sources, or a stable placeholder if no provider exists."""
        captured_at = datetime.now(UTC).isoformat()
        if not self.config.web_search_api_url:
            return tool_result(
                ok=True,
                data={
                    "available": False,
                    "web_sources": [],
                    "query": query,
                    "topic": topic,
                    "target_audience": target_audience,
                    "reason": "web_search_api_url_not_configured",
                    "captured_at": captured_at,
                },
                trace={
                    "tool": self.name,
                    "mode": "placeholder",
                    "function_call_ready": True,
                },
            )

        logger.info("WebSearchTool provider configured but adapter is not implemented")
        return tool_result(
            ok=True,
            data={
                "available": False,
                "web_sources": [],
                "query": query,
                "topic": topic,
                "target_audience": target_audience,
                "reason": "web_search_adapter_not_implemented",
                "captured_at": captured_at,
            },
            trace={
                "tool": self.name,
                "mode": "provider_placeholder",
                "provider_url_configured": True,
                "function_call_ready": True,
            },
        )


class DouyinTrendTool:
    """Retrieve Douyin trend signals for short-drama topic enrichment."""

    name = "douyin_trend_hotlist"
    description = (
        "Fetch Douyin hot topics or rising trends to enrich short-drama hooks "
        "and conflict design."
    )

    def __init__(self, config: Settings | None = None):
        self.config = config or settings

    def run(
        self,
        *,
        keyword: str = "",
        category: str = "hot",
        limit: int = 10,
        region: str = "CN",
    ) -> ToolResult:
        """Return normalized trend items, or a stable placeholder if no provider exists."""
        captured_at = datetime.now(UTC).isoformat()
        if not self.config.douyin_trend_api_url:
            return tool_result(
                ok=True,
                data={
                    "available": False,
                    "trend_items": [],
                    "keyword": keyword,
                    "category": category,
                    "region": region,
                    "reason": "douyin_trend_api_url_not_configured",
                    "captured_at": captured_at,
                },
                trace={
                    "tool": self.name,
                    "mode": "placeholder",
                    "function_call_ready": True,
                },
            )

        logger.info("DouyinTrendTool provider configured but adapter is not implemented")
        return tool_result(
            ok=True,
            data={
                "available": False,
                "trend_items": [],
                "keyword": keyword,
                "category": category,
                "region": region,
                "reason": "douyin_trend_adapter_not_implemented",
                "captured_at": captured_at,
            },
            trace={
                "tool": self.name,
                "mode": "provider_placeholder",
                "provider_url_configured": True,
                "function_call_ready": True,
            },
        )


def aggregate_external_context(
    *,
    query: str,
    web_result: ToolResult,
    douyin_result: ToolResult,
) -> dict[str, Any]:
    """Normalize external tool outputs into planner-ready context."""
    web_sources = web_result.get("data", {}).get("web_sources") or []
    trend_items = douyin_result.get("data", {}).get("trend_items") or []
    context_cards: list[dict[str, Any]] = []

    for item in web_sources:
        if isinstance(item, dict):
            context_cards.append({"source_type": "web", **item})
    for item in trend_items:
        if isinstance(item, dict):
            context_cards.append({"source_type": "douyin_trend", **item})

    return {
        "available": bool(context_cards),
        "query": query,
        "context_cards": context_cards,
        "creative_angles": [
            "当内部素材不足时，可将外部热点作为题材语境参考，但不得直接搬运来源文本。",
            "若后续接入真实热榜 API，可将高热度话题转化为短剧开场钩子和核心冲突。",
        ],
        "tool_results": {
            "web_search": web_result,
            "douyin_trend": douyin_result,
        },
    }


def _web_search_function(
    query: str,
    topic: str = "",
    target_audience: str = "",
    max_results: int = 5,
) -> dict[str, Any]:
    return WebSearchTool().run(
        query=query,
        topic=topic,
        target_audience=target_audience,
        max_results=max_results,
    )


def _douyin_trend_function(
    keyword: str = "",
    category: str = "hot",
    limit: int = 10,
    region: str = "CN",
) -> dict[str, Any]:
    return DouyinTrendTool().run(
        keyword=keyword,
        category=category,
        limit=limit,
        region=region,
    )


def build_external_content_function_tools() -> list[StructuredTool]:
    """Build LangChain StructuredTool wrappers for future ToolNode/function calling."""
    return [
        StructuredTool.from_function(
            func=_web_search_function,
            name=WebSearchTool.name,
            description=WebSearchTool.description,
            args_schema=WebSearchInput,
        ),
        StructuredTool.from_function(
            func=_douyin_trend_function,
            name=DouyinTrendTool.name,
            description=DouyinTrendTool.description,
            args_schema=DouyinTrendInput,
        ),
    ]
