/** TypeScript mirrors of the ACCE FastAPI JSON contracts. */

export type JobStatus = "pending" | "running" | "succeeded" | "failed";

export interface UserInputDto {
  topic: string;
  instructions?: string[];
  duration?: number | null;
  style?: string | null;
}

export interface ArtifactWrittenDto {
  stage: string;
  name: string;
  path: string;
}

export interface StageResultDto {
  stage: string;
  ok: boolean;
  retries: number;
  artifacts_written: ArtifactWrittenDto[];
  error?: string | null;
  duration_ms: number;
  output?: Record<string, unknown> | null;
}

/** `ctx.dump()` — the full job snapshot. */
export interface JobSnapshot {
  job_id: string;
  input: UserInputDto;
  status: JobStatus;
  current_stage?: string | null;
  results: Record<string, StageResultDto>;
  errors: string[];
  started_at?: number | null;
  finished_at?: number | null;
}

/** `GET /api/jobs/{id}` response body. */
export interface JobRecordDto {
  job_id: string;
  status: JobStatus;
  current_stage?: string | null;
  logs: string[];
  result?: JobSnapshot | null;
  error?: string | null;
}

/** One entry in `GET /api/jobs` (project list). */
export interface JobSummary {
  job_id: string;
  status: string;
  created_at: number;
  topic: string;
  score?: number | null;
  /** Poster frame URL (e.g. `/artifacts/.../production/thumbnail.jpg`), when present. */
  thumbnail?: string | null;
}

/** One entry in `GET /api/jobs/{id}/artifacts`. */
export interface ArtifactDto {
  stage: string;
  name: string;
  path: string;
  url: string;
  size: number;
  mime: string;
}

/** Background-music bed selected for a job (`GET /api/jobs/{id}/music`). */
export interface MusicDto {
  title: string;
  provider?: string | null;
  license?: string | null;
  bpm?: number | null;
  duration?: number | null;
  url: string;
}

export interface HealthDto {
  status: string;
  app: string;
  version: string;
}

export interface QualityIssueDto {
  level: "info" | "warning" | "error";
  stage: string;
  message: string;
  code: string;
  suggested_fix?: string | null;
}

export interface QualityReportDto {
  passed: boolean;
  score: number;
  issues: QualityIssueDto[];
  warnings: number;
  errors: number;
  recommended_retry_stage?: string | null;
  metadata: Record<string, unknown>;
  summary: string;
}

/** Canonical stage order + display labels. */
export const STAGES = [
  "research",
  "script",
  "scenes",
  "shots",
  "media",
  "audio",
  "production",
  "quality",
] as const;

export const STAGE_LABELS: Record<string, string> = {
  research: "Research",
  script: "Script",
  scenes: "Scene Planner",
  shots: "Shot Planner",
  media: "Media",
  audio: "Audio",
  production: "Production",
  quality: "Quality",
};
