"""Storyboard manual edit persistence tests."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api import storyboard_routes
from src.api.server import app
from src.core.database import Base, StoryboardDB
from src.storyboard.bridge import script_data_to_episode


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


class _TestDatabase:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get_session(self):
        return self._session_factory()


def _script_data():
    return {
        "title": "雨夜书店",
        "totalShots": 2,
        "totalDuration": "7.0 秒",
        "style": "anime",
        "requirements": "一个少年在雨夜发现神秘书店",
        "synopsis": "少年被雨夜书店吸引。",
        "packagingStyle": "悬疑动画",
        "characters": [
            {
                "id": "c1",
                "name": "少年",
                "role": "主角",
                "appearance": {"age": "17", "identity": "学生", "features": "蓝色雨衣"},
                "voice": "紧张",
                "description": "好奇心强",
            }
        ],
        "scenes": [{"id": "s1", "name": "旧街", "description": "雨夜街角"}],
        "props": [],
        "shots": [
            {
                "id": 1,
                "duration": "3.0s",
                "summary": "少年靠近书店",
                "narration": "",
                "hasNarration": False,
                "visualDesc": "少年撑伞走向书店",
                "shotName": "靠近",
            },
            {
                "id": 2,
                "duration": "4.0s",
                "summary": "书页翻动",
                "narration": "",
                "hasNarration": False,
                "visualDesc": "旧书自动翻页",
                "shotName": "翻页",
            },
        ],
        "aigcSpec": {
            "shots": [
                {
                    "id": 1,
                    "render_spec": {
                        "location": "雨夜旧街",
                        "shot_type": "medium shot",
                        "angle": "eye level",
                        "movement": "slow push-in",
                    },
                }
            ]
        },
    }


def test_manual_edits_endpoint_updates_storyboard_and_script_content(monkeypatch):
    session_factory = _session_factory()
    monkeypatch.setattr(storyboard_routes, "get_database", lambda: _TestDatabase(session_factory))

    seed_session = session_factory()
    episode = script_data_to_episode(seed_session, _script_data(), "thread-1")
    episode_id = episode.id
    seed_session.close()

    client = TestClient(app)
    response = client.put(
        f"/api/v1/storyboard/episodes/{episode_id}/manual-edits",
        json={
            "characters": [
                {
                    "id": "c1",
                    "name": "少女",
                    "voice": "清冷但紧张",
                    "appearance": "黑色雨衣，手握旧钥匙",
                }
            ],
            "shots": [
                {
                    "storyboard_number": 1,
                    "summary": "少女停在书店门口",
                    "visual_desc": "少女穿黑色雨衣，停在发光的旧书店门前",
                    "narration": "她意识到这家书店正在等她。",
                    "tags": ["雨夜", "悬疑"],
                    "duration_seconds": 6.5,
                    "start_frame_url": "oss://manual/start.png",
                    "end_frame_url": "oss://manual/end.png",
                    "keyframe_urls": ["oss://manual/key.png"],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["updated_storyboards"] == 1
    assert response.json()["updated_characters"] == 1

    verify_session = session_factory()
    stored_episode = verify_session.get(type(episode), episode_id)
    stored_storyboard = (
        verify_session.query(StoryboardDB)
        .filter(StoryboardDB.episode_id == episode_id, StoryboardDB.storyboard_number == 1)
        .one()
    )
    script_content = json.loads(stored_episode.script_content)

    assert stored_storyboard.action == "少女穿黑色雨衣，停在发光的旧书店门前"
    assert stored_storyboard.dialogue == "她意识到这家书店正在等她。"
    assert stored_storyboard.duration == 7
    assert "少女穿黑色雨衣" in stored_storyboard.image_prompt
    assert "她意识到这家书店正在等她" in stored_storyboard.video_prompt
    assert stored_storyboard.image_url == "oss://manual/start.png"
    assert stored_storyboard.render_spec["human_reviewed"] is True
    assert stored_storyboard.render_spec["manual_media"]["keyframe_urls"] == ["oss://manual/key.png"]

    assert script_content["characters"][0]["name"] == "少女"
    assert script_content["characters"][0]["appearance"]["features"] == "黑色雨衣，手握旧钥匙"
    assert script_content["shots"][0]["summary"] == "少女停在书店门口"
    assert script_content["shots"][0]["hasNarration"] is True
    assert script_content["totalDuration"] == "10.5 秒"
    assert stored_episode.duration == 11
    verify_session.close()
