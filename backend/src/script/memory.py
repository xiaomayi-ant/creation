"""Structured memory store for the script generation workflow."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.core.database import ScriptThreadMemoryDB, get_database
from src.core.logger import get_logger

logger = get_logger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_retrieval_references(payload: dict[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for item in _as_list(payload.get("retrieval_references")):
        if not isinstance(item, dict):
            continue
        references.append(
            {
                "rank": item.get("rank"),
                "novel_name": item.get("novel_name"),
                "novel_id": item.get("novel_id"),
                "node_id": item.get("node_id"),
                "chapter_title": item.get("chapter_title"),
                "chapter_summary": item.get("chapter_summary"),
                "llm_reference_excerpt": str(item.get("llm_reference_excerpt") or "")[:500],
            }
        )
    return references


def build_thread_summary(payload: dict[str, Any]) -> str:
    """Build a compact deterministic summary for future context injection."""
    user_input = str(payload.get("user_input") or "").strip()
    script_config = _as_dict(payload.get("script_config"))
    script_plan = _as_dict(payload.get("script_plan"))
    verification = _as_dict(payload.get("verification_result"))
    review = _as_dict(payload.get("quality_review_result"))
    source_trace = _as_dict(payload.get("source_ref_trace"))
    move_codebook = _as_dict(payload.get("move_codebook"))

    constraints = _as_dict(script_plan.get("constraints"))
    moves = _as_list(move_codebook.get("moves"))
    scene_plan = _as_list(script_plan.get("scene_plan"))
    references = _clean_retrieval_references(payload)

    parts = [
        f"User request: {user_input or '(empty)'}",
        "Config: "
        + ", ".join(
            str(v)
            for v in [
                script_config.get("ratio") or constraints.get("ratio"),
                script_config.get("style") or constraints.get("style"),
                script_config.get("duration") or constraints.get("duration"),
                script_config.get("mood") or constraints.get("mood"),
                script_config.get("density") or constraints.get("density"),
            ]
            if v
        ),
        f"Plan: {len(scene_plan)} shots/scenes planned.",
        f"References: {len(references)} retrieved, {source_trace.get('used_ref_count', 0)} used.",
        f"Moves: {len(moves)} extracted.",
        (
            "Verification: "
            f"{'passed' if verification.get('passed') else 'failed/unknown'}"
            f", score={verification.get('score', 'n/a')}."
        ),
        (
            "Review: "
            f"{'passed' if review.get('passed') else 'failed/unknown'}"
            f", score={review.get('overall_score', 'n/a')}."
        ),
        f"Revision count: {payload.get('revision_count', 0)}.",
    ]
    final_result = _as_dict(payload.get("final_result"))
    content = str(final_result.get("content") or "").strip()
    if content:
        parts.append("Final script excerpt: " + content[:500])
    return "\n".join(parts)


def memory_record_to_dict(record: ScriptThreadMemoryDB) -> dict[str, Any]:
    """Serialize a memory ORM record for application use."""
    return {
        "id": record.id,
        "thread_id": record.thread_id,
        "user_input": record.user_input,
        "selections": record.selections or {},
        "script_config": record.script_config or {},
        "retrieval_references": record.retrieval_references or [],
        "move_codebook": record.move_codebook,
        "script_plan": record.script_plan,
        "verification_result": record.verification_result,
        "quality_review_result": record.quality_review_result,
        "source_ref_trace": record.source_ref_trace,
        "final_result": record.final_result,
        "final_script": record.final_script,
        "thread_summary": record.thread_summary,
        "revision_count": record.revision_count,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def upsert_script_thread_memory(
    thread_id: str,
    payload: dict[str, Any],
    *,
    session: Session | None = None,
) -> dict[str, Any]:
    """Persist latest structured memory for a script generation thread."""
    owns_session = session is None
    if session is None:
        session = get_database().get_session()

    try:
        record = (
            session.query(ScriptThreadMemoryDB)
            .filter(ScriptThreadMemoryDB.thread_id == thread_id)
            .one_or_none()
        )
        if record is None:
            record = ScriptThreadMemoryDB(thread_id=thread_id)
            session.add(record)

        final_result = _as_dict(payload.get("final_result"))
        record.user_input = str(payload.get("user_input") or "")
        record.selections = _as_dict(payload.get("selections"))
        record.script_config = _as_dict(payload.get("script_config"))
        record.retrieval_references = _clean_retrieval_references(payload)
        record.move_codebook = payload.get("move_codebook")
        record.script_plan = payload.get("script_plan")
        record.verification_result = payload.get("verification_result")
        record.quality_review_result = payload.get("quality_review_result")
        record.source_ref_trace = payload.get("source_ref_trace")
        record.final_result = final_result
        record.final_script = str(final_result.get("content") or "")
        record.thread_summary = build_thread_summary(payload)
        record.revision_count = int(payload.get("revision_count") or 0)

        session.commit()
        session.refresh(record)
        return memory_record_to_dict(record)
    except Exception:
        session.rollback()
        logger.exception("Failed to persist script thread memory: thread_id=%s", thread_id)
        raise
    finally:
        if owns_session:
            session.close()


def get_script_thread_memory(
    thread_id: str,
    *,
    session: Session | None = None,
) -> dict[str, Any] | None:
    """Load latest structured memory for a script generation thread."""
    owns_session = session is None
    if session is None:
        session = get_database().get_session()

    try:
        record = (
            session.query(ScriptThreadMemoryDB)
            .filter(ScriptThreadMemoryDB.thread_id == thread_id)
            .one_or_none()
        )
        return memory_record_to_dict(record) if record else None
    finally:
        if owns_session:
            session.close()
