---
name: douyin_short_drama_style
description: Use this skill after retrieval, Move extraction, and story planning when the user asks for Douyin-style short drama, viral mobile short-video pacing, high-conflict reversals, explosive hooks, or platform-native short-drama expression.
license: MIT
compatibility: Optional sample crawler is a placeholder until a compliant public/provider API is configured.
allowed-tools: web_search_external_context douyin_trend_hotlist short_drama_sample_crawler
metadata:
  version: "0.1.0"
  platform: douyin
  phase: expression_style
---

# Douyin Short Drama Style

## Purpose

Adapt a fixed story plan and Move structure into Douyin-style short-drama expression.

This skill must not change upstream retrieval, Move extraction, or the planned story logic. It only affects expression: hook shape, pacing, dialogue pressure, shot emphasis, and mobile-first clarity.

## When To Use

Use this skill after:

1. Internal RAG retrieval has completed.
2. Move extraction has completed.
3. `script_plan` exists.
4. The user asks for Douyin, viral short drama, high-conflict pacing, strong reversals, or "baokuan" style.

Do not use this skill for slow literary narration, long-form novel writing, or low-conflict brand copy.

## Style Rules

- The first shot must show visible pressure, contradiction, or danger.
- Prefer action and conflict over background exposition.
- Lines should be short, emotional, and easy to understand on mobile.
- Escalate tension every 1-2 shots.
- Use clear reversal, identity gap, cliffhanger, or secret exposure.
- Make character stakes visible: money, family, status, betrayal, survival, reputation, or love.
- Keep shot descriptions concrete enough for AIGC execution.
- Avoid copying external sample wording, titles, character names, or plot sequences.

## Rewrite Rules

- Convert abstract emotion into visible behavior.
- Convert backstory into conflict shown on screen.
- Put the strongest contradiction in the first 3 seconds.
- If a shot only explains context, rewrite it into an action or confrontation.
- If dialogue is literary, rewrite it into short spoken lines with pressure.

## Using Sample Scripts

The optional `scripts/fetch_samples.py` placeholder represents a future sample crawler or provider adapter.

If sample scripts are available:

1. Use them only as structural references.
2. Extract hook type, conflict type, reversal style, pacing, and cliffhanger pattern.
3. Do not copy exact text or plot.
4. Convert sample patterns into original choices that fit the current `script_plan`.

Reference schema: `references/sample_schema.json`.

## Output Influence

When this skill is active, the writer should strengthen:

- `script_plan.external_context.creative_angles`
- first-shot hook
- conflict visibility
- short dialogue pressure
- reversal and cliffhanger design
- mobile-first AIGC visual clarity
