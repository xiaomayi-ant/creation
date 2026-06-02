"""Current script graph plan-and-execute tests."""

import src.script.nodes as script_nodes
from src.script.graph import create_script_graph
from src.script.nodes import (
    plan_story_node,
    review_script_node,
    verify_script_node,
    write_scenes_node,
)
from src.script.review_agent import normalize_review_result


def _base_state(**overrides):
    state = {
        "user_input": "一个少年在雨夜发现神秘书店",
        "user_instructions": "",
        "target_duration_sec": 30,
        "target_chapters": 1,
        "script_config": {
            "ratio": "16:9横屏",
            "style": "动漫风",
            "narrator": "需要旁白",
            "mood": "intense",
            "duration": "30秒",
            "density": "balanced",
        },
        "thread_summary": None,
        "previous_thread_memory": None,
        "reference_novel_title": None,
        "reference_novel_data": None,
        "retrieval_results": [
            {
                "novel_id": "novel-a",
                "node_id": "node-1",
                "novel_name": "参考小说",
                "content": "雨夜，主角进入一间神秘书店。",
                "tree_node": {
                    "title": "雨夜书店",
                    "summary": "主角在雨夜被神秘书店吸引。",
                },
            }
        ],
        "move_codebook": {
            "moves": [
                {
                    "move_id": 1,
                    "name": "hook",
                    "description": "用异常事件建立悬念",
                    "emotional_beats": ["mystery", "tension"],
                }
            ]
        },
        "story_ir": None,
        "script_plan": None,
        "plan_text": None,
        "draft_script": None,
        "final_script": None,
        "verification_result": None,
        "quality_review_result": None,
        "revision_feedback": None,
        "iteration_count": 0,
        "revision_count": 0,
        "messages": [],
        "error": None,
    }
    state.update(overrides)
    return state


def _valid_final_script():
    return """
## 剧本概览
故事核心：少年在雨夜发现神秘书店。

## 分镜设计
- **雨夜街角** - 少年撑伞靠近亮灯书店。

## 视觉风格
冷雨、暖光、悬疑动画风。

## AIGC执行规格(JSON)
{
  "reference_trace": {
    "retrieval_refs": ["novel-a#node-1"],
    "used_refs": ["novel-a#node-1"],
    "unused_refs": [],
    "unused_reasons": [],
    "overall_reason": "参考雨夜悬疑氛围"
  },
  "characters": [{"name": "少年", "role": "主角", "appearance": {}, "voice": "", "description": ""}],
  "scenes": [{"name": "雨夜街角", "description": "雨中的旧街"}],
  "props": [],
  "shots": [
    {"id": 1, "summary": "少年靠近书店", "visualDesc": "雨夜街角，少年撑伞前行", "duration": "4.0s", "source_refs": ["novel-a#node-1"], "source_reason": "参考雨夜悬疑氛围", "no_source_reason": ""},
    {"id": 2, "summary": "暖光亮起", "visualDesc": "书店门缝透出暖光", "duration": "4.0s", "source_refs": [], "source_reason": "", "no_source_reason": "原创承接"},
    {"id": 3, "summary": "旧书翻动", "visualDesc": "柜台上的旧书自动翻页", "duration": "4.0s", "source_refs": [], "source_reason": "", "no_source_reason": "原创推进"},
    {"id": 4, "summary": "少年进入", "visualDesc": "少年推门进入书店", "duration": "4.0s", "source_refs": [], "source_reason": "", "no_source_reason": "原创收束"}
  ]
}
"""


def test_create_script_graph_with_verify_node():
    graph = create_script_graph(with_memory=False)
    assert graph is not None


def test_plan_story_node_builds_script_plan_from_references():
    result = plan_story_node(_base_state(), {})
    plan = result["script_plan"]

    assert plan["goal"] == "一个少年在雨夜发现神秘书店"
    assert plan["references"][0]["ref_id"] == "novel-a#node-1"
    assert plan["scene_plan"]
    assert plan["scene_plan"][0]["source_refs"] == ["novel-a#node-1"]


def test_plan_story_node_includes_thread_summary_memory():
    result = plan_story_node(
        _base_state(thread_summary="上一轮确认：主角是女高中生，书店会在午夜出现。"),
        {},
    )

    memory_context = result["script_plan"]["memory_context"]
    assert "女高中生" in memory_context["thread_summary"]
    assert "同一 thread_id" in memory_context["use_hint"]


def test_write_scenes_node_injects_thread_summary_into_prompt(monkeypatch):
    class FakeLLM:
        def stream(self, _messages, config=None):
            class Chunk:
                content = "## 剧本概览\n测试"

            yield Chunk()

    monkeypatch.setattr(script_nodes, "get_llm", lambda temperature=None: FakeLLM())

    result = write_scenes_node(
        _base_state(
            script_plan={"goal": "测试"},
            thread_summary="上一轮确认：保留雨夜书店和旧书自动翻页。",
        ),
        {},
    )

    assert "历史压缩上下文" in result["prompt_used"]
    assert "旧书自动翻页" in result["prompt_used"]


def test_verify_script_node_accepts_valid_aigc_json():
    result = verify_script_node(_base_state(final_script=_valid_final_script()))

    assert result["verification_result"]["passed"] is True


def test_verify_script_node_routes_invalid_json_to_revision():
    result = verify_script_node(_base_state(final_script="## 剧本概览\n无 JSON"))

    assert result["verification_result"]["passed"] is False
    assert result["revision_count"] == 1


def test_review_script_node_skips_subagent_when_structure_fails():
    verified = verify_script_node(_base_state(final_script="## 剧本概览\n无 JSON"))

    command = review_script_node({**_base_state(), **verified})

    assert command.goto == "write_scenes"
    assert command.update["quality_review_result"]["review_skipped"] is True
    assert "AIGC执行规格" in command.update["revision_feedback"]


def test_review_script_node_uses_command_for_semantic_rewrite(monkeypatch):
    def fake_review_subagent(_input_state):
        return {
            "passed": False,
            "review_available": True,
            "alignment_score": 5,
            "fluency_score": 7,
            "story_consistency_score": 6,
            "aigc_executability_score": 8,
            "overall_score": 65,
            "issues": [
                {
                    "type": "alignment",
                    "severity": "major",
                    "message": "没有突出用户要求的神秘书店。",
                }
            ],
            "revision_feedback": "强化神秘书店设定，并让每个镜头围绕该悬念推进。",
            "summary": "需要重写以贴合用户意图。",
        }

    monkeypatch.setattr(script_nodes, "run_review_subagent", fake_review_subagent)
    verified = verify_script_node(_base_state(final_script=_valid_final_script()))

    command = review_script_node({**_base_state(final_script=_valid_final_script()), **verified})

    assert command.goto == "write_scenes"
    assert command.update["revision_count"] == 1
    assert command.update["quality_review_result"]["overall_score"] == 65
    assert "神秘书店" in command.update["revision_feedback"]


def test_normalize_review_result_parses_fenced_json():
    result = normalize_review_result(
        """```json
        {
          "passed": true,
          "alignment_score": 9,
          "fluency_score": 8,
          "story_consistency_score": 8,
          "aigc_executability_score": 9,
          "overall_score": 84,
          "issues": [],
          "revision_feedback": "",
          "summary": "通过"
        }
        ```"""
    )

    assert result["passed"] is True
    assert result["review_available"] is True
    assert result["overall_score"] == 84
