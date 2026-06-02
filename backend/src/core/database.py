"""数据库模型 - SQLite 存储"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Text, Integer, Float, JSON, DateTime, ForeignKey, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

Base = declarative_base()


class MoveCodebookDB(Base):
    """Move Codebook 存储模型"""
    __tablename__ = "move_codebooks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_novel = Column(String(200), nullable=False, index=True)
    source_author = Column(String(100))
    move_id = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    name_cn = Column(String(100))
    description = Column(Text)
    description_cn = Column(Text)
    emotional_beats = Column(JSON, default=list)
    core_idea = Column(Text)
    chapters = Column(JSON, default=list)
    estimated_words = Column(JSON)
    source_excerpts = Column(JSON, default=list)
    story_framework = Column(String(200))
    pacing = Column(JSON)
    raw_codebook = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<MoveCodebook {self.source_novel}:{self.move_id}:{self.name}>"


class StoryIRDB(Base):
    """Story IR 存储模型"""
    __tablename__ = "story_irs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False)
    concept = Column(Text)
    chapters = Column(JSON, default=list)
    reference_codebook_id = Column(String(36))
    reference_novel = Column(String(200))
    total_chapters = Column(Integer)
    total_words = Column(Integer)
    status = Column(String(50), default="planning")
    thread_id = Column(String(100), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<StoryIR {self.title}>"


class ScriptThreadMemoryDB(Base):
    """短剧线程记忆模型"""
    __tablename__ = "script_thread_memories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id = Column(String(100), nullable=False, unique=True, index=True)
    user_input = Column(Text, default="", nullable=False)
    selections = Column(JSON, default=dict)
    script_config = Column(JSON, default=dict)
    retrieval_references = Column(JSON, default=list)
    move_codebook = Column(JSON)
    script_plan = Column(JSON)
    verification_result = Column(JSON)
    quality_review_result = Column(JSON)
    source_ref_trace = Column(JSON)
    final_result = Column(JSON)
    final_script = Column(Text, default="", nullable=False)
    thread_summary = Column(Text, default="", nullable=False)
    revision_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ScriptThreadMemory {self.thread_id}>"


class GeneratedChapterDB(Base):
    """生成的章节内容存储模型"""
    __tablename__ = "generated_chapters"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    story_ir_id = Column(String(36), nullable=False, index=True)
    chapter_num = Column(Integer, nullable=False)
    title = Column(String(200))
    content = Column(Text)
    word_count = Column(Integer)
    fluency_score = Column(Float)
    fluency_issues = Column(JSON, default=list)
    iteration_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<GeneratedChapter {self.story_ir_id}:{self.chapter_num}>"


class EpisodeDB(Base):
    """剧集模型"""
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    script_content = Column(Text, default="", nullable=False)
    thread_id = Column(String(100), index=True)
    duration = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    storyboards = relationship("StoryboardDB", back_populates="episode", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Episode {self.id}:{self.title}>"


class StoryboardDB(Base):
    """分镜模型"""
    __tablename__ = "storyboards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    episode_id = Column(Integer, ForeignKey("episodes.id"), index=True, nullable=False)
    storyboard_number = Column(Integer, nullable=False)
    title = Column(String(255), default="", nullable=False)
    location = Column(String(255), default="", nullable=False)
    shot_type = Column(String(100), default="", nullable=False)
    angle = Column(String(100), default="", nullable=False)
    movement = Column(String(100), default="", nullable=False)
    action = Column(Text, default="", nullable=False)
    dialogue = Column(Text, default="", nullable=False)
    duration = Column(Integer, default=5, nullable=False)
    image_prompt = Column(Text, default="", nullable=False)
    video_prompt = Column(Text, default="", nullable=False)
    render_spec = Column(JSON, default=dict)
    image_url = Column(String(500), default="", nullable=False)
    video_url = Column(String(500), default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    episode = relationship("EpisodeDB", back_populates="storyboards")

    def __repr__(self):
        return f"<Storyboard {self.episode_id}:{self.storyboard_number}>"


class AsyncTaskDB(Base):
    """异步任务状态模型"""
    __tablename__ = "async_tasks"

    id = Column(String(64), primary_key=True)
    type = Column(String(64), nullable=False)
    status = Column(String(32), default="pending", nullable=False)
    progress = Column(Integer, default=0, nullable=False)
    resource_id = Column(String(64), nullable=False)
    message = Column(String(255), default="", nullable=False)
    result = Column(Text, default="", nullable=False)
    error = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AsyncTask {self.id}:{self.type}:{self.status}>"


_db_logger = logging.getLogger(__name__)


def _ensure_aigc_columns(engine) -> None:
    """为 storyboards 表补充 image_url / video_url 列（SQLite 迁移）。"""
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(storyboards)")).fetchall()
        existing = {row[1] for row in rows}

        for col_name in ("image_url", "video_url"):
            if col_name not in existing:
                conn.execute(text(
                    f"ALTER TABLE storyboards ADD COLUMN {col_name} VARCHAR(500) NOT NULL DEFAULT ''"
                ))
                _db_logger.info("已添加 storyboards.%s 列", col_name)
        conn.commit()


class Database:
    """SQLite 数据库管理器"""

    _instance: Optional["Database"] = None

    def __new__(cls, db_path: str = "data/writer.db"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = "data/writer.db"):
        if self._initialized:
            return
        
        if not os.path.isabs(db_path):
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(project_root, db_path)
        
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        _ensure_aigc_columns(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._initialized = True

    def get_session(self) -> Session:
        return self.SessionLocal()

    def close(self):
        if hasattr(self, "engine"):
            self.engine.dispose()


def get_database(db_path: str = "data/writer.db") -> Database:
    return Database(db_path)


def save_move_codebook(
    session: Session,
    novel_title: str,
    novel_author: str,
    codebook: dict,
) -> str:
    """保存 Move Codebook"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        codebook_id = str(uuid.uuid4())
        moves = codebook.get("moves", [])
        logger.info(f"开始保存 Move Codebook: {novel_title}, 共 {len(moves)} 个 Move")

        existing = session.query(MoveCodebookDB).filter(
            MoveCodebookDB.source_novel == novel_title
        ).all()
        if existing:
            existing_ids = set(r.id for r in existing)
            for eid in existing_ids:
                session.query(MoveCodebookDB).filter(MoveCodebookDB.id == eid).delete()
            logger.info(f"已清理之前的 {len(existing_ids)} 条记录")

        for move in moves:
            record = MoveCodebookDB(
                id=str(uuid.uuid4()),
                source_novel=novel_title,
                source_author=novel_author,
                move_id=move.get("move_id"),
                name=move.get("name"),
                name_cn=move.get("name_cn"),
                description=move.get("description"),
                description_cn=move.get("description_cn"),
                emotional_beats=move.get("emotional_beats", []),
                core_idea=move.get("core_idea"),
                chapters=move.get("chapters", []),
                estimated_words=move.get("estimated_words"),
                source_excerpts=move.get("source_excerpts", []),
                story_framework=codebook.get("story_framework"),
                pacing=codebook.get("pacing"),
                raw_codebook=codebook,
            )
            session.add(record)

        session.commit()
        logger.info(f"Move Codebook 保存成功: {codebook_id}")
        return codebook_id
    except Exception as e:
        session.rollback()
        logger.error(f"保存 Move Codebook 失败: {e}")
        raise


def save_story_ir(
    session: Session,
    title: str,
    concept: str,
    chapters: list,
    reference_novel: str,
    reference_codebook_id: str,
    thread_id: str,
) -> str:
    """保存 Story IR"""
    record = StoryIRDB(
        title=title,
        concept=concept,
        chapters=chapters,
        reference_novel=reference_novel,
        reference_codebook_id=reference_codebook_id,
        total_chapters=len(chapters),
        thread_id=thread_id,
    )
    session.add(record)
    session.commit()
    return record.id


def update_story_ir_status(
    session: Session,
    story_ir_id: str,
    status: str,
    total_words: int = None,
):
    """更新 Story IR 状态"""
    story = session.get(StoryIRDB, story_ir_id)
    if story:
        story.status = status
        if total_words is not None:
            story.total_words = total_words
        session.commit()


def save_generated_chapter(
    session: Session,
    story_ir_id: str,
    chapter_num: int,
    title: str,
    content: str,
    fluency_score: float,
    fluency_issues: list,
    iteration_count: int,
) -> str:
    """保存生成的章节"""
    record = GeneratedChapterDB(
        story_ir_id=story_ir_id,
        chapter_num=chapter_num,
        title=title,
        content=content,
        word_count=len(content),
        fluency_score=fluency_score,
        fluency_issues=fluency_issues,
        iteration_count=iteration_count,
    )
    session.add(record)
    session.commit()
    return record.id


def get_move_codebooks_by_novel(session: Session, novel_title: str) -> list:
    """获取某小说的 Move Codebook"""
    return session.query(MoveCodebookDB).filter(
        MoveCodebookDB.source_novel == novel_title
    ).all()


def get_story_by_thread(session: Session, thread_id: str) -> Optional[StoryIRDB]:
    """根据 thread_id 获取故事"""
    return session.query(StoryIRDB).filter(
        StoryIRDB.thread_id == thread_id
    ).order_by(StoryIRDB.created_at.desc()).first()
