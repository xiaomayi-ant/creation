---
name: xiaohongshu_story_style
description: Use this skill after retrieval, Move extraction, and story planning when the user asks for Xiaohongshu-style storytelling, emotional value, lifestyle scenes, relationship topics, soft sharing tone, or realistic personal-experience short drama.
license: MIT
compatibility: Optional sample crawler is a placeholder until a compliant public/provider API is configured.
allowed-tools: web_search_external_context short_drama_sample_crawler
metadata:
  version: "0.1.0"
  platform: xiaohongshu
  phase: expression_style
---

# Xiaohongshu Story Style

## Purpose

Adapt a fixed story plan and Move structure into Xiaohongshu-style emotional storytelling.

This skill must not change upstream retrieval, Move extraction, or the planned story logic. It only affects expression: tone, scene texture, emotional framing, dialogue softness, and lifestyle detail.

## When To Use

Use this skill after:

1. Internal RAG retrieval has completed.
2. Move extraction has completed.
3. `script_plan` exists.
4. The user asks for Xiaohongshu, lifestyle storytelling, emotional value, relationship resonance, daily-life texture, or personal sharing style.

Do not use this skill for high-conflict revenge drama, hard-selling ads, or pure action spectacle.

## Style Rules

- Prefer lived-in details over loud exposition.
- Make conflict emotionally relatable, not only dramatic.
- Use soft first-person or close third-person narration when appropriate.
- Ground scenes in daily-life objects, habits, weather, rooms, messages, meals, mirrors, bags, coffee, elevators, or commuting.
- Dialogue should sound like real conversation or private reflection.
- Emotional value matters: self-respect, healing, boundaries, growth, companionship, or quiet realization.
- Reversals should feel like recognition or emotional release, not only shock.
- Avoid directly copying external post wording, titles, personal stories, or brand phrasing.

## Rewrite Rules

- Convert generic conflict into a specific relationship moment.
- Convert abstract emotion into a concrete lifestyle detail.
- If a shot is too loud, make it more intimate and observational.
- If dialogue sounds theatrical, rewrite it as natural speech or internal monologue.
- Keep AIGC visual descriptions concrete, warm, and scene-grounded.

## Using Sample Scripts

The optional `scripts/fetch_samples.py` placeholder represents a future sample crawler or provider adapter.

If sample scripts or posts are available:

1. Use them only as tone and structure references.
2. Extract emotional theme, scene texture, narration stance, and relationship tension.
3. Do not copy exact wording, personal stories, titles, or brand phrases.
4. Transform sample patterns into original short-drama expression that fits the current `script_plan`.

Reference schema: `references/sample_schema.json`.

## Output Influence

When this skill is active, the writer should strengthen:

- emotional framing
- daily-life scene texture
- natural spoken dialogue
- personal sharing tone
- relationship resonance
- visual details that are warm, specific, and executable
