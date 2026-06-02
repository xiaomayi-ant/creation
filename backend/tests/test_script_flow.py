"""Current script graph plan-and-execute tests."""

from src.script.graph import create_script_graph
from src.script.nodes import plan_story_node, verify_script_node, route_after_verify


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
        "revision_feedback": None,
        "iteration_count": 0,
        "revision_count": 0,
        "messages": [],
        "error": None,
    }
    state.update(overrides)
    return state


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


def test_verify_script_node_accepts_valid_aigc_json():
    final_script = """
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
    result = verify_script_node(_base_state(final_script=final_script))

    assert result["verification_result"]["passed"] is True
    assert route_after_verify({**_base_state(), **result}) == "finalize"


def test_verify_script_node_routes_invalid_json_to_revision():
    result = verify_script_node(_base_state(final_script="## 剧本概览\n无 JSON"))

    assert result["verification_result"]["passed"] is False
    assert result["revision_count"] == 1
    assert route_after_verify({**_base_state(), **result}) == "revise"
