"""API surface tests for the current script/storyboard workflow."""

from fastapi.testclient import TestClient

from src.api.server import app


def test_openapi_exposes_current_script_storyboard_workflow_only():
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])

    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/submit" in paths
    assert "/api/v1/chat/memory/{thread_id}" in paths
    assert "/api/v1/storyboard/episodes/from-script" in paths
    assert "/api/v1/storyboard/episodes/{episode_id}/manual-edits" in paths
    assert "/api/v1/storyboard/episodes/{episode_id}/generate-aigc" in paths

    assert "/api/v1/generate" not in paths
    assert "/api/v1/generate/stream" not in paths
    assert "/api/v1/analyze" not in paths
    assert "/api/v1/novel/generate" not in paths
    assert "/api/v1/novel/generate/stream" not in paths
