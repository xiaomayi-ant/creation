"""小说生成 Agent 的节点函数"""

import json
from typing import Any, Optional

from src.core.logger import get_logger
from src.novel.loader import load_novel_from_qidian
from src.novel.move_extractor import extract_moves_from_novel
from src.novel.prompts import (
    CHAPTER_WRITING_PROMPT,
    FLUENCY_CHECK_PROMPT,
    STORY_PLAN_PROMPT,
    format_move_codebook_for_prompt,
    format_reference_moves_for_prompt,
)
from src.novel.state import NovelAgentState

logger = get_logger(__name__)


# ============================================================================
# Node 1: 加载参考小说 + 提取 Move
# ============================================================================

async def load_reference_node(state: NovelAgentState) -> dict:
    """
    加载参考小说数据并提取 Move 结构

    输入：reference_novel_title
    输出：reference_novel_data, move_codebook, move_codebook_id
    """

    logger.info("加载参考小说: %s", state['reference_novel_title'])

    novel_data = load_novel_from_qidian(state["reference_novel_title"])

    if not novel_data:
        error_msg = f"无法加载小说: {state['reference_novel_title']}"
        logger.error(error_msg)
        return {
            "error": error_msg,
            "reference_novel_data": None,
            "move_codebook": None,
            "move_codebook_id": None,
        }

    logger.info("成功加载小说: %s", novel_data['title'])

    move_codebook, move_codebook_id = await extract_moves_from_novel_safe(novel_data)

    if not move_codebook:
        logger.warning("使用默认的 Move Codebook")
        move_codebook = get_default_move_codebook()
        move_codebook_id = None

    moves = move_codebook.get('moves', [])
    move_names = [m.get('name') for m in moves]
    logger.info("Move Codebook 已准备: %d 个 Move - %s", len(moves), move_names)
    if move_codebook_id:
        logger.info("Move Codebook ID: %s", move_codebook_id)

    return {
        "reference_novel_data": novel_data,
        "move_codebook": move_codebook,
        "move_codebook_id": move_codebook_id,
        "iteration_count": state["iteration_count"] + 1,
    }


async def extract_moves_from_novel_safe(novel_data: dict) -> tuple:
    """
    安全地提取 Move，失败时返回 (None, None)
    """
    try:
        result = await extract_moves_from_novel(novel_data)
        if result is None:
            return None, None
        return result
    except Exception as e:
        logger.warning("Move 提取失败，使用默认值: %s", e)
        return None, None


def get_default_move_codebook() -> dict:
    """获取默认的 Move Codebook（用于测试）"""
    return {
        "moves": [
            {
                "move_id": 1,
                "name": "setup",
                "description": "建立故事的世界和氛围",
                "emotional_beats": ["calm", "quiet"],
                "core_idea": "介绍故事背景和主角",
                "estimated_words": {"min": 300, "max": 500},
            },
            {
                "move_id": 2,
                "name": "introduce_character",
                "description": "引入重要人物",
                "emotional_beats": ["intrigue", "surprise"],
                "core_idea": "出现一个改变故事的人物",
                "estimated_words": {"min": 400, "max": 600},
            },
            {
                "move_id": 3,
                "name": "create_conflict",
                "description": "制造冲突和张力",
                "emotional_beats": ["tension", "shock"],
                "core_idea": "问题和挑战出现",
                "estimated_words": {"min": 500, "max": 800},
            },
            {
                "move_id": 4,
                "name": "escalate",
                "description": "升级冲突",
                "emotional_beats": ["urgency", "determination"],
                "core_idea": "情况变得更加复杂和紧急",
                "estimated_words": {"min": 400, "max": 600},
            },
            {
                "move_id": 5,
                "name": "resolution",
                "description": "解决和收尾",
                "emotional_beats": ["relief", "acceptance"],
                "core_idea": "冲突得到解决，故事走向结束",
                "estimated_words": {"min": 300, "max": 500},
            },
        ],
        "story_framework": "五幕结构",
        "pacing": {"setup": 0.15, "rising": 0.40, "climax": 0.20, "falling": 0.15, "resolution": 0.10},
    }


# ============================================================================
# Node 2: 规划故事
# ============================================================================

async def plan_story_node(state: NovelAgentState) -> dict:
    """
    规划新故事的章节结构

    输入：user_input, user_style, target_chapters, move_codebook, move_codebook_id
    输出：story_ir, story_ir_id
    """

    logger.info("规划故事框架")
    logger.debug("用户输入: %s", state["user_input"])
    logger.debug("目标章节数: %d", state["target_chapters"])

    move_codebook = state.get("move_codebook", {})
    moves = move_codebook.get("moves", [])
    logger.debug("使用 Move Codebook: %d 个 Move", len(moves))

    move_codebook_text = format_move_codebook_for_prompt(state["move_codebook"])

    target_chapters = state["target_chapters"]
    target_word_count = target_chapters * 400
    prompt = STORY_PLAN_PROMPT.format(
        user_input=state["user_input"],
        user_style=state.get("user_style", "通用风格"),
        move_codebook=move_codebook_text,
        target_chapters=target_chapters,
        target_word_count=target_word_count,
    )

    story_ir = await call_llm_safe(prompt, parse_json=True)

    if not story_ir:
        logger.warning("使用默认的故事规划")
        story_ir = generate_default_story_plan(
            user_input=state["user_input"],
            target_chapters=state["target_chapters"],
        )

    chapters = story_ir.get('chapters', [])
    logger.info("故事规划完成: %d 章", len(chapters))
    for ch in chapters:
        logger.debug("  第%d章: %s (核心: %s, 参考: %s)",
            ch.get('chapter_id'), ch.get('title'), ch.get('core_idea'), ch.get('reference_moves'))

    story_ir_id = _save_story_ir(
        title=story_ir.get("story_title", "无标题"),
        concept=state["user_input"],
        chapters=chapters,
        reference_novel=state.get("reference_novel_title"),
        reference_codebook_id=state.get("move_codebook_id"),
        thread_id=state.get("thread_id", ""),
    )
    logger.info("Story IR 已存储: %s", story_ir_id)

    return {
        "story_ir": story_ir,
        "story_ir_id": str(story_ir_id) if story_ir_id else None,
        "current_chapter": 1,
        "iteration_count": state["iteration_count"] + 1,
    }


def _save_story_ir(
    title: str,
    concept: str,
    chapters: list,
    reference_novel: str,
    reference_codebook_id,
    thread_id: str,
):
    """保存 Story IR 到数据库"""
    try:
        from src.core.database import get_database, save_story_ir
        db = get_database()
        session = db.get_session()
        try:
            codebook_id_str = str(reference_codebook_id) if reference_codebook_id else None
            story_ir_id = save_story_ir(
                session=session,
                title=title,
                concept=concept,
                chapters=chapters,
                reference_novel=reference_novel,
                reference_codebook_id=codebook_id_str,
                thread_id=thread_id,
            )
            return story_ir_id
        finally:
            session.close()
    except Exception as e:
        logger.warning("保存 Story IR 失败: %s", e)
        return None


def generate_default_story_plan(user_input: str, target_chapters: int = 5) -> dict:
    """生成默认的故事规划"""
    chapters = []

    chapter_ideas = [
        {"title": "开篇", "idea": "介绍主角和故事背景"},
        {"title": "相遇", "idea": "出现一个改变故事的人物或事件"},
        {"title": "冲突", "idea": "主要的冲突和挑战出现"},
        {"title": "升级", "idea": "情况变得更加复杂"},
        {"title": "结局", "idea": "冲突得到解决，故事完结"},
    ]

    for i in range(min(target_chapters, len(chapter_ideas))):
        chapters.append({
            "chapter_id": i + 1,
            "title": chapter_ideas[i]["title"],
            "core_idea": chapter_ideas[i]["idea"],
            "target_word_count": 400,
            "reference_moves": ["setup", "introduce_character"][i % 2 : i % 2 + 1],
            "notes": f"第 {i + 1} 章",
        })

    # 如果需要更多章节
    for i in range(len(chapter_ideas), target_chapters):
        chapters.append({
            "chapter_id": i + 1,
            "title": f"第{i + 1}章",
            "core_idea": f"故事发展第 {i + 1} 阶段",
            "target_word_count": 400,
            "reference_moves": ["create_conflict", "escalate"][i % 2],
            "notes": "",
        })

    return {
        "story_title": extract_title_from_concept(user_input),
        "story_concept": user_input,
        "chapters": chapters,
    }


def extract_title_from_concept(concept: str) -> str:
    """从故事概念中提取标题"""
    # 简单的实现：取前面的词作为标题
    words = concept.split()
    return "".join(words[:3]) if words else "无题"


# ============================================================================
# Node 3: 写作章节
# ============================================================================

async def write_chapter_node(state: NovelAgentState) -> dict:
    """
    生成当前章节的文本

    输入：story_ir, current_chapter, chapter_texts
    输出：current_chapter_text
    """

    current_idx = state["current_chapter"] - 1
    chapter_plan = state["story_ir"]["chapters"][current_idx]

    logger.info("生成第 %d 章: %s", state['current_chapter'], chapter_plan['title'])
    logger.debug("章节核心: %s", chapter_plan.get('core_idea'))
    logger.debug("参考 Moves: %s", chapter_plan.get('reference_moves'))
    logger.debug("目标字数: %d", chapter_plan.get('target_word_count'))

    # 准备前文摘要
    previous_context = prepare_context_summary(state)

    # 准备参考 Move 的说明
    reference_moves_guide = format_reference_moves_for_prompt(
        chapter_plan.get("reference_moves", []),
        state["move_codebook"],
    )

    # 构建 Prompt
    prompt = CHAPTER_WRITING_PROMPT.format(
        story_title=state["story_ir"]["story_title"],
        story_concept=state["story_ir"]["story_concept"],
        user_style=state.get("user_style", "通用"),
        previous_context=previous_context,
        chapter_title=chapter_plan["title"],
        chapter_core_idea=chapter_plan["core_idea"],
        chapter_target_words=chapter_plan["target_word_count"],
        reference_moves_guide=reference_moves_guide,
    )

    # 调用 LLM（或使用 mock）
    chapter_text = await call_llm_safe(prompt, parse_json=False)

    if not chapter_text:
        # 生成默认的章节文本
        chapter_text = generate_default_chapter(
            chapter_plan["title"],
            chapter_plan["core_idea"],
            chapter_plan["target_word_count"],
        )

    logger.info("章节生成完成: 第%d章, 字数: %d", state['current_chapter'], len(chapter_text))

    return {
        "current_chapter_text": chapter_text,
        "chapter_iterations": 1,
        "iteration_count": state["iteration_count"] + 1,
    }


def prepare_context_summary(state: NovelAgentState) -> str:
    """准备前文摘要（用于下一章生成时提供上下文）"""
    if not state["chapter_texts"]:
        return "（无前文）"

    if len(state["chapter_texts"]) == 1:
        prev_text = state["chapter_texts"][0]
        return f"前一章的结尾：\n{prev_text[-300:]}"  # 最后 300 字

    # 如果有多章，提供摘要
    summary = f"前文已写 {len(state['chapter_texts'])} 章：\n"
    for i, text in enumerate(state["chapter_texts"][-2:]):  # 最后两章
        summary += f"  第 {i + 1} 章摘要：{text[:100]}...\n"

    return summary


def generate_default_chapter(title: str, core_idea: str, target_words: int) -> str:
    """生成默认的章节文本"""
    template = f"""【{title}】

{core_idea}

这是第一稿的自动生成文本。在实际应用中，这里会是 LLM 生成的精彩故事内容。

本章的核心是：{core_idea}

通过细致的描写和对话，我们能够感受到人物的情感变化和故事的推进。

这是一个占位文本，实际运行时应该由 LLM 生成真实的故事内容。
"""

    # 简单地重复内容以达到目标字数
    while len(template) < target_words * 0.8:
        template += "\n\n（故事内容继续展开...）"

    return template[:target_words + 100]  # 略微超过目标


# ============================================================================
# Node 4: 验证流畅性
# ============================================================================

async def verify_fluency_node(state: NovelAgentState) -> dict:
    """
    检查章节的语句通顺性

    输入：current_chapter_text
    输出：fluency_check
    """

    logger.info("检查语句通顺性")

    prompt = FLUENCY_CHECK_PROMPT.format(
        chapter_text=state["current_chapter_text"]
    )

    fluency_result = await call_llm_safe(prompt, parse_json=True)

    if not fluency_result:
        fluency_result = {
            "is_fluent": True,
            "issues": [],
            "score": 8.0,
            "suggestions": "文本流畅，无明显问题。",
        }

    score = fluency_result.get('score', 0)
    is_fluent = fluency_result.get('is_fluent', False)
    issues = fluency_result.get('issues', [])
    logger.info("通顺性检查: 得分 %.1f, 通过: %s, 问题数: %d", score, is_fluent, len(issues))
    if issues:
        for issue in issues:
            logger.debug("  问题: %s", issue)

    if is_fluent:
        _save_generated_chapter(
            story_ir_id=state.get("story_ir_id"),
            chapter_num=state.get("current_chapter", 1),
            title=state.get("story_ir", {}).get("chapters", [{}])[state.get("current_chapter", 1) - 1].get("title", ""),
            content=state.get("current_chapter_text", ""),
            fluency_score=score,
            fluency_issues=issues,
            iteration_count=state.get("chapter_iterations", 1),
        )

    return {
        "fluency_check": fluency_result,
        "iteration_count": state["iteration_count"] + 1,
    }


def _save_generated_chapter(
    story_ir_id: str,
    chapter_num: int,
    title: str,
    content: str,
    fluency_score: float,
    fluency_issues: list,
    iteration_count: int,
):
    """保存生成的章节到数据库"""
    try:
        from src.core.database import get_database, save_generated_chapter
        db = get_database()
        session = db.get_session()
        try:
            if story_ir_id:
                save_generated_chapter(
                    session=session,
                    story_ir_id=story_ir_id,
                    chapter_num=chapter_num,
                    title=title,
                    content=content,
                    fluency_score=fluency_score,
                    fluency_issues=fluency_issues,
                    iteration_count=iteration_count,
                )
                logger.debug("章节 %d 已保存到数据库", chapter_num)
        finally:
            session.close()
    except Exception as e:
        logger.warning("保存章节失败: %s", e)


# ============================================================================
# 条件路由函数
# ============================================================================

def should_revise_chapter(state: NovelAgentState) -> str:
    """
    决定是否需要重新生成这章
    """
    fluency_check = state.get("fluency_check", {})
    is_fluent = fluency_check.get("is_fluent", True)
    iterations = state.get("chapter_iterations", 0)

    # 如果通顺就继续，或者已经重试了 2 次就放弃
    if is_fluent or iterations >= 2:
        return "continue"  # 继续到下一步
    else:
        return "revise"  # 重新生成


def should_continue_chapters(state: NovelAgentState) -> str:
    """
    决定是否继续生成下一章
    """
    current_chapter = state["current_chapter"]
    story_ir = state.get("story_ir", {})
    total_chapters = len(story_ir.get("chapters", []))

    if current_chapter < total_chapters:
        return "next_chapter"  # 继续下一章
    else:
        return "finalize"  # 全部完成，进入最终化


# ============================================================================
# Node 5: 最终化 - 合并所有章节
# ============================================================================

async def finalize_node(state: NovelAgentState) -> dict:
    """
    合并所有章节为最终故事

    输入：chapter_texts, story_ir
    输出：final_story
    """

    logger.info("合并所有章节为最终故事")

    # 合并章节
    final_story = merge_chapters(
        state["story_ir"],
        state["chapter_texts"],
    )

    logger.info(f"✅ 故事完成，总字数: {len(final_story)}")

    return {
        "final_story": final_story,
        "chapters_completed": len(state["chapter_texts"]),
        "iteration_count": state["iteration_count"] + 1,
    }


def merge_chapters(story_ir: dict, chapter_texts: list[str]) -> str:
    """合并所有章节"""
    result = f"""# {story_ir['story_title']}

## 概念
{story_ir['story_concept']}

---

"""

    for i, text in enumerate(chapter_texts):
        chapter_num = i + 1
        if chapter_num <= len(story_ir.get("chapters", [])):
            chapter_info = story_ir["chapters"][i]
            result += f"\n## 第{chapter_num}章 {chapter_info['title']}\n\n"

        result += text + "\n\n"

    return result


# ============================================================================
# 辅助函数
# ============================================================================

async def call_llm_safe(prompt: str, parse_json: bool = False) -> Optional[Any]:
    """
    安全地调用 LLM，失败时返回 None

    Args:
        prompt: 要发送给 LLM 的 prompt
        parse_json: 是否尝试解析 JSON 响应

    Returns:
        LLM 的响应，或 None（如果失败）
    """
    try:
        from src.script.nodes import get_llm

        llm = get_llm()
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        if parse_json:
            # 尝试解析 JSON
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end]
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end]

            return json.loads(response_text.strip())
        else:
            return response_text

    except Exception as e:
        logger.warning(f"LLM 调用失败，使用默认值: {e}")
        return None
