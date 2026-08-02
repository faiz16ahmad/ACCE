/** Typed client for the ACCE FastAPI backend. */

import type { ArtifactDto, HealthDto, JobRecordDto, JobSummary, MusicDto, UserInputDto } from "./types";

export const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

let apiBase = DEFAULT_API_BASE;

export function getApiBase(): string {
  return apiBase;
}

export function setApiBase(base: string): void {
  apiBase = base.trim().replace(/\/+$/, "");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    throw new Error(`GET ${path} → ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthDto>("/api/health"),

  createJob: (input: UserInputDto) =>
    request<{ job_id: string }>("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),

  getJob: (jobId: string) => request<JobRecordDto>(`/api/jobs/${encodeURIComponent(jobId)}`),

  getJobs: () => request<{ jobs: JobSummary[] }>("/api/jobs"),

  getArtifacts: (jobId: string) =>
    request<{ artifacts: ArtifactDto[] }>(`/api/jobs/${encodeURIComponent(jobId)}/artifacts`),

  getMusic: (jobId: string) =>
    request<{ music: MusicDto | null }>(`/api/jobs/${encodeURIComponent(jobId)}/music`),
};

/** Absolute URL for a job's music stream (from `MusicDto.url`). */
export function musicUrl(url: string): string {
  return `${apiBase}${url}`;
}

/** Turn an artifact `url` (e.g. `/artifacts/job-x/production/final_video.mp4`) into an absolute URL. */
export function artifactUrl(url: string): string {
  return `${apiBase}${url}`;
}
