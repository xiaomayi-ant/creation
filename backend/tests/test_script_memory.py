"""Script thread memory store tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.database import Base
from src.script.memory import (
    build_thread_summary,
    get_script_thread_memory,
    upsert_script_thread_memory,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _payload(**overrides):
    payload = {
        "thread_id": "thread-1",
        "user_input": "一个少年在雨夜发现神秘书店",
        "selections": {"style": "anime"},
        "script_config": {"ratio": "16:9横屏", "style": "动漫风", "duration": "30秒"},
        "retrieval_references": [
            {
                "rank": 1,
                "novel_name": "参考小说",
                "novel_id": "novel-a",
                "node_id": "node-1",
                "chapter_title": "雨夜书店",
                "chapter_summary": "主角在雨夜被神秘书店吸引。",
                "llm_reference_excerpt": "雨夜，主角进入一间神秘书店。",
                "chapter_content": "不应该进入 thread memory 的完整原文",
            }
        ],
        "move_codebook": {"moves": [{"move_id": 1, "name": "hook"}]},
        "script_plan": {
            "constraints": {"style": "动漫风"},
            "scene_plan": [{"id": 1}, {"id": 2}],
        },
        "verification_result": {"passed": True, "score": 92},
        "quality_review_result": {"passed": True, "overall_score": 86},
        "source_ref_trace": {"used_ref_count": 1},
        "revision_count": 1,
        "final_result": {"content": "## 剧本概览\n少年进入神秘书店。"},
    }
    payload.update(overrides)
    return payload


def test_build_thread_summary_compacts_generation_state():
    summary = build_thread_summary(_payload())

    assert "User request: 一个少年在雨夜发现神秘书店" in summary
    assert "Plan: 2 shots/scenes planned." in summary
    assert "References: 1 retrieved, 1 used." in summary
    assert "Review: passed, score=86." in summary


def test_upsert_script_thread_memory_sanitizes_and_updates():
    session = _session()

    first = upsert_script_thread_memory("thread-1", _payload(), session=session)
    second = upsert_script_thread_memory(
        "thread-1",
        _payload(user_input="改成女主进入神秘书店", revision_count=2),
        session=session,
    )

    assert first["thread_id"] == "thread-1"
    assert second["user_input"] == "改成女主进入神秘书店"
    assert second["revision_count"] == 2
    assert len(second["retrieval_references"]) == 1
    assert "chapter_content" not in second["retrieval_references"][0]


def test_get_script_thread_memory_returns_latest_record():
    session = _session()
    upsert_script_thread_memory("thread-1", _payload(), session=session)

    memory = get_script_thread_memory("thread-1", session=session)

    assert memory is not None
    assert memory["thread_id"] == "thread-1"
    assert "少年进入神秘书店" in memory["final_script"]
