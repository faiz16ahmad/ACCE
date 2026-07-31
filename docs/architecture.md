# ACCE V1 — Architecture

## Pipeline

```mermaid
flowchart LR
    UI[User Input] --> R[Research]
    R --> S[Script]
    S --> SC[Scene Planner]
    SC --> M[Media Search]
    M --> A[Audio]
    A --> P[Production]
    P --> Q[Quality Check]
    Q --> OUT[Output Artifacts]
```

Each stage is one module implementing the `StageModule` contract
(`validate_input` → `run` → `validate_output`). The `PipelineOrchestrator`
executes modules in `Stage` definition order; a failed stage is retried
*on its own* (default 2 retries) before the job fails.

## Layer diagram

```mermaid
flowchart TD
    subgraph Orchestrator["core"]
        ORC[PipelineOrchestrator]
        CTX[JobContext]
    end

    subgraph Modules["modules/"]
        M1[research]
        M2[script]
        M3[scenes]
        M4[media]
        M5[audio]
        M6[production]
        M7[quality]
    end

    subgraph Providers["providers/"]
        P1[LLMProvider]
        P2[ImageProvider]
        P3[VideoProvider]
        P4[MusicProvider]
        P5[TTSProvider]
        REG[registry + stubs]
    end

    subgraph Memory["memory/"]
        CACHE[DiskCache]
        STORE[ArtifactStore]
    end

    ORC --> Modules
    Modules --> CTX
    Modules --> Providers
    Modules --> STORE
    Providers --> CACHE
    STORE --> CACHE
    P1 -.-> REG
    P2 -.-> REG
    P3 -.-> REG
    P4 -.-> REG
    P5 -.-> REG
```

Rules:

- No module calls an external API directly — only provider interfaces.
- No module resolves globals — dependencies are injected via constructors
  (`modules.factory.build_orchestrator`).
- Every module writes its output into `out/<job_id>/<stage>/` via
  `ArtifactStore`.

## Job sequence

```mermaid
sequenceDiagram
    participant U as User
    participant O as Orchestrator
    participant M as StageModule
    participant S as ArtifactStore
    participant P as Provider

    U->>O: run(UserInput)
    loop for each Stage
        O->>M: validate_input(ctx)
        M-->>O: ok
        O->>M: run(ctx)
        M->>P: provider call (interface)
        P-->>M: result
        M->>S: save_json(stage, file)
        M-->>O: StageResult(output, artifacts)
        O->>M: validate_output(result)
        O->>O: emit ProgressEvent
    end
    O-->>U: JobContext(status, results)
```

## Artifact flow

```mermaid
flowchart LR
    R[research.json] --> S[script.json]
    S --> SC[scenes.json]
    SC --> M[media.json + scene_XX.json]
    SC --> A[mix_plan.json + narration_XX + master_audio]
    R --> P[title.txt / description.txt]
    SC --> P[subtitles.srt]
    A --> P[final.mp4]
    P --> Q[report.json]
```

## Audio: beat-sync-ready seam

The audio stage produces a timestamped `AudioMixPlan` (list of `MixSegment`s)
and hands it to an `AudioEngine` that renders the master track:

```mermaid
flowchart LR
    N[narration tracks] --> PL[AudioMixPlan]
    MU[music track with bpm] --> PL
    PL --> EN[AudioEngine]
    EN --> MASTER[master audio]
```

V2 beat-synchronization changes **only** how the plan's segment timings are
computed (music `bpm` → beat-aligned boundaries) inside
`DefaultAudioModule._build_mix_plan`. The plan contract, the engine, and all
downstream consumers stay unchanged.
