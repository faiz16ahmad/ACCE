/** Typed client for the ACCE FastAPI backend. */

import type {
  ArtifactDto,
  DirectorSnapshotDto,
  ExportRecordDto,
  HealthDto,
  JobRecordDto,
  JobSummary,
  LanguageDto,
  MusicDto,
  MusicTrackDto,
  UserInputDto,
} from "./types";

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
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string" && body.detail) detail = body.detail;
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthDto>("/api/health"),

  getLanguages: () => request<{ languages: LanguageDto[] }>("/api/languages"),

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

  // -- Director Mode ----------------------------------------------------------

  getDirector: (jobId: string) =>
    request<DirectorSnapshotDto>(`/api/jobs/${encodeURIComponent(jobId)}/director`),

  setDirectorMusic: (
    jobId: string,
    body: {
      mode: string;
      track_id?: string | null;
      volume?: number;
      fade_in?: number;
      fade_out?: number;
      duck?: boolean;
      loop?: boolean;
    },
  ) =>
    request<{ state: DirectorSnapshotDto["state"]; current_track: MusicTrackDto | null }>(
      `/api/jobs/${encodeURIComponent(jobId)}/director/music`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),

  uploadDirectorTrack: async (jobId: string, file: File, name: string = "") => {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("name", name);
    return request<{ state: DirectorSnapshotDto["state"]; library: MusicTrackDto[] }>(
      `/api/jobs/${encodeURIComponent(jobId)}/director/upload`,
      { method: "POST", body: form },
    );
  },

  renameUploadTrack: (trackId: string, name: string) =>
    request<{ track: MusicTrackDto | null }>(
      `/api/music/library/upload/${encodeURIComponent(trackId)}/name`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      },
    ),

  previewDirector: (jobId: string) =>
    request<{ preview_url: string }>(
      `/api/jobs/${encodeURIComponent(jobId)}/director/preview`,
      { method: "POST" },
    ),

  exportDirector: (jobId: string) =>
    request<{ export: ExportRecordDto }>(
      `/api/jobs/${encodeURIComponent(jobId)}/director/export`,
      { method: "POST" },
    ),

  getDirectorExports: (jobId: string) =>
    request<{ exports: ExportRecordDto[] }>(
      `/api/jobs/${encodeURIComponent(jobId)}/exports`,
    ),

  deleteDirectorExport: (jobId: string, exportId: string) =>
    request<{ deleted: string }>(
      `/api/jobs/${encodeURIComponent(jobId)}/exports/${encodeURIComponent(exportId)}`,
      { method: "DELETE" },
    ),

  // -- Music Library ----------------------------------------------------------

  getMusicLibrary: (query?: string) => {
    const params = query ? `?q=${encodeURIComponent(query)}` : "";
    return request<{ tracks: MusicTrackDto[] }>(`/api/music/library${params}`);
  },
};

/** Absolute URL for a job's music stream (from `MusicDto.url`). */
export function musicUrl(url: string): string {
  return `${apiBase}${url}`;
}

/** Absolute URL for any library track's stream endpoint. */
export function libraryTrackUrl(trackId: string): string {
  return `${apiBase}/api/music/library/${encodeURIComponent(trackId)}/stream`;
}

/** Turn an artifact `url` (e.g. `/artifacts/job-x/production/final_video.mp4`) into an absolute URL. */
export function artifactUrl(url: string): string {
  return `${apiBase}${url}`;
}
