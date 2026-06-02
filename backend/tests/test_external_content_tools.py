"""External content tool tests."""

from src.tools.external_content_tools import (
    DouyinTrendTool,
    WebSearchTool,
    build_external_content_function_tools,
)


def test_external_content_tools_return_placeholder_results_without_provider():
    web_result = WebSearchTool().run(query="最近热门短剧题材")
    trend_result = DouyinTrendTool().run(keyword="短剧反转")

    assert web_result["ok"] is True
    assert web_result["data"]["available"] is False
    assert web_result["data"]["reason"] == "web_search_api_url_not_configured"
    assert web_result["trace"]["function_call_ready"] is True

    assert trend_result["ok"] is True
    assert trend_result["data"]["available"] is False
    assert trend_result["data"]["reason"] == "douyin_trend_api_url_not_configured"
    assert trend_result["trace"]["function_call_ready"] is True


def test_external_content_tools_expose_structured_function_call_wrappers():
    tools = build_external_content_function_tools()
    tool_names = {tool.name for tool in tools}

    assert tool_names == {"web_search_external_context", "douyin_trend_hotlist"}

    web_tool = next(tool for tool in tools if tool.name == "web_search_external_context")
    result = web_tool.invoke({"query": "抖音爆款家庭短剧"})

    assert result["ok"] is True
    assert result["data"]["query"] == "抖音爆款家庭短剧"
    assert result["trace"]["function_call_ready"] is True
