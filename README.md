<div align="center">

# AI Short Drama Creation Space
### LangGraph + FastAPI + React Agentic Workflow for Short-Drama Production

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Workflow-121212?style=for-the-badge)](https://github.com/langchain-ai/langgraph)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=111111)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vite.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)

</div>

<hr>

<p align="center">
  <a href="./backend/src/script">Script Agent</a> |
  <a href="./backend/src/storyboard">Storyboard</a> |
  <a href="./backend/src/retrieval">Retrieval</a> |
  <a href="./backend/skills">Skills</a> |
  <a href="./backend/.env.example">Backend Env</a> |
  <a href="./frontend/.env.example">Frontend Env</a> |
  <a href="./docker-compose.yml">Docker Compose</a>
</p>

> [!NOTE]
> The current `main` branch is the cleaned portfolio-ready workflow. Legacy public APIs for copywriting and novel generation have been removed from the API surface; the active product path is short-drama generation plus storyboard/AIGC production.

## Introduction

AI Short Drama Creation Space is a full-stack creative production system for short-drama scripts and AIGC storyboard assets.

The platform connects a **LangGraph Plan-and-Execute backend** with a **React creative workspace**. Users submit a creative requirement, confirm generation options, stream the Agent execution result, create storyboard episodes, manually revise shots, and trigger asynchronous AIGC/video tasks.

## Highlights

- **Agentic workflow**: reference loading, external enrichment, story planning, script execution, semantic review, bounded rewriting, and finalization.
- **Hybrid RAG**: Qdrant vector retrieval + MongoDB/PageIndex metadata + OSS source text for traceable references.
- **ReviewSubagent**: LangGraph subgraph for semantic review, connected to the parent graph through `Command`-driven routing.
- **Memory + Compact**: durable thread memory for user intent, selections, move codebook, review result, and deterministic thread summary.
- **Tool layer**: WebSearchTool and DouyinTrendTool placeholders for external trend enrichment when internal RAG is insufficient.
- **Platform Skills**: Douyin short-drama style and Xiaohongshu story-style skill packages for channel-specific expression.
- **Human-in-the-loop**: storyboard manual edits are persisted before AIGC generation, keeping human changes in the backend production chain.
- **Async production**: Redis/Celery handles storyboard generation, AIGC image/video generation, and video merge tasks.

## Architecture

```text
Browser
  -> Frontend (React + Vite + Tailwind)
      -> /api/v1/chat/submit (SSE)
          -> FastAPI Backend
              -> LangGraph Script Agent
                  -> load_reference
                      -> Qdrant + PageIndex/MongoDB + OSS
                  -> external_enrichment
                      -> WebSearchTool / DouyinTrendTool
                  -> plan_story
                  -> write_scenes
                  -> ReviewSubagent
                      -> semantic review + rewrite decision
                  -> finalize
              -> Thread Memory + Compact Summary
      -> Storyboard APIs
          -> Episode / Shot persistence
          -> Manual edits (HITL)
          -> Celery tasks
              -> storyboard generation
              -> AIGC image/video generation
              -> FFmpeg video merge
```

## Core Modules

| Module | Path | Description |
| --- | --- | --- |
| Script Agent | `backend/src/script/` | LangGraph Plan-and-Execute short-drama generation workflow |
| Review Subagent | `backend/src/script/review_agent.py` | Semantic review subgraph for alignment, fluency, continuity, and AIGC feasibility |
| Memory | `backend/src/script/memory.py` | Thread-level memory and deterministic compact summary persistence |
| Retrieval | `backend/src/retrieval/` | Qdrant + MongoDB/PageIndex + OSS hybrid reference retrieval |
| Tools | `backend/src/tools/` | External content enrichment tools and function-call compatible wrappers |
| Skills | `backend/skills/` | Platform style skill packages for Douyin and Xiaohongshu |
| Storyboard | `backend/src/storyboard/` | Episode conversion, storyboard persistence, AIGC tasks, and video merge |
| Frontend | `frontend/` | React workspace for generation, storyboard editing, task polling, and preview |

## Product Flow

```text
User requirement
  -> Config confirmation
  -> SSE script generation
  -> Structured script data
  -> Episode + storyboard creation
  -> Manual storyboard review/edit
  -> AIGC image/video task
  -> Video merge / preview
```

## Quick Start

### 1. Prerequisites

| Component | Version / Requirement |
| --- | --- |
| Python | 3.12+ |
| uv | Recommended Python package manager |
| Node.js | 18+ |
| npm | Comes with Node.js |
| Redis | Required for Celery async tasks |
| MongoDB | Optional, required for PageIndex/RAG metadata |
| Qdrant | Optional, required for vector retrieval |
| OSS | Optional, required for source text and generated media storage |

### 2. Backend

```bash
cd backend
uv sync
cp .env.example .env

# Edit backend/.env and configure at least one LLM provider.
uv run python main.py --serve
```

Backend defaults:

- API: `http://localhost:8000`
- Health: `http://localhost:8000/api/v1/health`
- OpenAPI: `http://localhost:8000/docs`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend defaults:

- App: `http://localhost:3000`
- API base: `VITE_API_BASE=/api`

### 4. Celery Worker

Redis/Celery is required for storyboard generation, AIGC media generation, and video merge tasks.

```bash
# terminal 1
redis-server

# terminal 2
cd backend
uv run celery -A src.core.celery_app worker --loglevel=info
```

For local synchronous testing, set:

```env
CELERY_TASK_ALWAYS_EAGER=true
```

## Environment

### Minimal Backend Settings

| Scope | Keys |
| --- | --- |
| LLM | `LLM_PROVIDER`, `DASHSCOPE_API_KEY` or `OPENAI_API_KEY`, `MODEL_NAME` |
| API | `API_HOST`, `API_PORT` |
| Runtime | `LOG_LEVEL`, `MAX_ITERATIONS`, `ENABLE_MOVE_PLANNER` |

### Optional Production Capabilities

| Capability | Keys |
| --- | --- |
| Hybrid RAG | `ENABLE_RETRIEVAL`, `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION`, `MONGODB_URI`, `MONGODB_DATABASE` |
| OSS Storage | `OSS_ENABLED`, `OSS_ACCESS_KEY_ID`, `OSS_ACCESS_KEY_SECRET`, `OSS_BUCKET_NAME`, `OSS_ENDPOINT` |
| External Tools | `ENABLE_EXTERNAL_CONTENT_TOOLS`, `WEB_SEARCH_API_URL`, `DOUYIN_TREND_API_URL` |
| AIGC | `AIGC_IMAGE_MODEL`, `AIGC_VIDEO_MODEL`, `DASHSCOPE_API_KEY` |
| Celery | `REDIS_URL`, `CELERY_TASK_ALWAYS_EAGER` |

## API Surface

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Backend health check |
| `POST` | `/api/v1/chat` | Return generation configuration form |
| `GET` | `/api/v1/chat/memory/{thread_id}` | Read persisted script thread memory |
| `POST` | `/api/v1/chat/submit` | Run script Agent and stream SSE events |
| `POST` | `/api/v1/storyboard/episodes` | Create an episode manually |
| `POST` | `/api/v1/storyboard/episodes/from-script` | Create episode and storyboard from script data |
| `POST` | `/api/v1/storyboard/episodes/storyboards` | Enqueue storyboard generation task |
| `PUT` | `/api/v1/storyboard/episodes/{episode_id}/manual-edits` | Persist human storyboard edits |
| `POST` | `/api/v1/storyboard/episodes/{episode_id}/generate-aigc` | Enqueue AIGC image/video generation task |
| `GET` | `/api/v1/storyboard/tasks/{task_id}` | Poll async task status |
| `POST` | `/api/v1/storyboard/videos/merge` | Enqueue video merge task |
| `POST` | `/api/v1/storyboard/videos/merge/precheck` | Validate merge inputs synchronously |

## Project Structure

```text
.
├── backend/
│   ├── main.py                         # Backend entry point
│   ├── pyproject.toml                  # uv project metadata
│   ├── skills/                         # Platform style skill packages
│   └── src/
│       ├── api/                        # FastAPI routes and schemas
│       ├── core/                       # Config, database, Celery, logging
│       ├── retrieval/                  # Qdrant/PageIndex/OSS retrieval
│       ├── script/                     # LangGraph script Agent
│       ├── storyboard/                 # Storyboard, AIGC, video tasks
│       └── tools/                      # External enrichment tools
├── frontend/
│   ├── src/App.tsx                     # Main creative workspace
│   ├── src/components/                 # Script and UI components
│   ├── src/services/api.ts             # Backend API client
│   └── package.json
├── .github/workflows/                  # Manual deployment workflows
├── docker-compose.yml
├── Caddyfile
├── DEPLOY.md
└── README.md
```

## Development

### Backend Checks

```bash
cd backend
uv run --extra dev pytest
uv run --extra dev ruff check .
```

### Frontend Checks

```bash
cd frontend
npm run lint
npm run build
```

### Docker Compose

```bash
docker compose up -d
docker compose logs -f backend
```

The bundled compose file starts backend, frontend, and Caddy. External services such as Redis, MongoDB, Qdrant, and OSS credentials should be provided separately according to the enabled features.

## Deployment

GitHub Actions deployment workflows are intentionally manual:

- `.github/workflows/deploy.yml`
- `.github/workflows/rawdep.yml`

They use `workflow_dispatch` only, so pushing to `main` will not automatically deploy to ECS.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `DASHSCOPE_API_KEY` or `OPENAI_API_KEY` missing | Configure `backend/.env` and restart the backend |
| SSE generation starts but retrieval is empty | Check `ENABLE_RETRIEVAL`, Qdrant, MongoDB, and OSS configuration |
| AIGC tasks stay pending | Start Redis and the Celery worker |
| Manual storyboard edits do not affect AIGC | Ensure edits are saved through `/manual-edits` before triggering AIGC |
| Deploy workflow fails with `missing server host` | Configure GitHub deployment secrets before manual run |

## License

This repository is currently maintained as a portfolio and learning project. Add a formal license before public reuse or redistribution.
