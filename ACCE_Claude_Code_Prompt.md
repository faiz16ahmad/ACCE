# ACCE V1 --- Claude Code Master Prompt

> **Goal:** Build Version 1 of the Autonomous Content Creation Engine
> (ACCE).

------------------------------------------------------------------------

# Your Role

You are a Principal Software Engineer.

Build a clean, modular, production-quality project.

Do **not** over-engineer.

Do **not** design a framework.

Do **not** build an operating system.

Focus only on delivering an excellent V1.

------------------------------------------------------------------------

# Project Goal

Input:

-   Topic
-   3--5 lines of instructions
-   Optional duration
-   Optional style

Output:

-   Research report
-   Engaging script
-   Scene timeline
-   Gathered visual assets
-   Voice narration
-   Subtitle file
-   Final MP4
-   Thumbnail
-   Title
-   Description

------------------------------------------------------------------------

# V1 Scope

The pipeline is:

    User Input
        │
        ▼
    Research
        │
        ▼
    Script
        │
        ▼
    Scene Planner
        │
        ▼
    Media Search
        │
        ▼
    Production
        │
        ▼
    Quality Check
        │
        ▼
    Output

Nothing else.

No marketplace.

No distributed runtime.

No autonomous CEO.

No multi-application support.

------------------------------------------------------------------------

# Architecture

                    User
                      │
                      ▼
            Workflow Orchestrator
                      │
     ┌────────────────┼────────────────┐
     ▼                ▼                ▼
    Research      Script         Scene Planner
                                         │
                                         ▼
                                   Media Search
                                         │
                                         ▼
                                  Video Builder
                                         │
                                         ▼
                                  Quality Checker
                                         │
                                         ▼
                                      Output

The Workflow Orchestrator simply executes modules in order.

------------------------------------------------------------------------

# Folder Structure

    acce/
    │
    ├── core/
    │   └── orchestrator.py
    │
    ├── modules/
    │   ├── research/
    │   ├── script/
    │   ├── scenes/
    │   ├── media/
    │   ├── production/
    │   └── quality/
    │
    ├── providers/
    ├── memory/
    ├── frontend/
    ├── config/
    ├── tests/
    ├── docs/
    └── main.py

------------------------------------------------------------------------

# Responsibilities

## Research

-   Collect reliable information.
-   Verify facts.
-   Return structured research.

Output:

``` json
{
  "topic":"",
  "facts":[],
  "sources":[],
  "summary":""
}
```

------------------------------------------------------------------------

## Script

Input:

Research JSON

Output:

-   Hook
-   Body
-   Ending
-   Narration script

------------------------------------------------------------------------

## Scene Planner

Convert script into scenes.

Each scene includes:

``` json
{
 "scene":1,
 "duration":5,
 "narration":"",
 "visual_description":"",
 "search_keywords":[]
}
```

------------------------------------------------------------------------

## Media Search

Retrieve media using provider interfaces.

Priority:

1.  Cache
2.  Pexels
3.  Pixabay
4.  Wikimedia

Return best asset per scene.

------------------------------------------------------------------------

## Production

Responsibilities:

-   Voice generation
-   Subtitle generation
-   Timeline assembly
-   FFmpeg rendering
-   Thumbnail generation

------------------------------------------------------------------------

## Quality

Check:

-   Missing assets
-   Script completeness
-   Subtitle timing
-   Render success

If a stage fails, retry only that stage.

------------------------------------------------------------------------

# Provider Layer

No module may call external APIs directly.

Use interfaces.

Example:

    LLMProvider
    ImageProvider
    VideoProvider
    TTSProvider

Implementations are hidden behind interfaces.

------------------------------------------------------------------------

# Memory

Keep it simple.

Cache:

-   research
-   downloaded assets
-   generated audio
-   subtitles

------------------------------------------------------------------------

# UI

Technology:

-   FastAPI
-   Next.js
-   Tailwind

Dashboard shows:

-   Current stage
-   Logs
-   Progress
-   Preview
-   Final download

------------------------------------------------------------------------

# Coding Rules

-   One responsibility per module.
-   Dependency injection where practical.
-   Type hints.
-   Pydantic models for contracts.
-   Logging throughout.
-   Configuration via .env.
-   Unit-test friendly.
-   No duplicated code.

------------------------------------------------------------------------

# Deliverables

Produce:

-   Complete folder structure
-   Core orchestrator
-   Interfaces
-   Empty module skeletons
-   Pydantic models
-   Configuration
-   README
-   Mermaid architecture diagrams
-   Development roadmap

Do **not** fully implement providers yet.

Create a clean foundation that can be implemented module-by-module.

------------------------------------------------------------------------

# Milestones

1.  Skeleton project
2.  Research module
3.  Script module
4.  Scene planner
5.  Media search
6.  Production
7.  Quality
8.  UI
9.  End-to-end integration

Success means V1 can generate a publishable YouTube video from a topic
with minimal manual work.
