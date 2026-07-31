"use client";

/** Polls `GET /api/jobs/{id}` while the job is pending/running. */

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { JobRecordDto } from "@/lib/types";

const POLL_MS = 800;

export function useJob(jobId: string | null) {
  const [job, setJob] = useState<JobRecordDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const stopped = useRef(false);

  const terminal =
    job !== null && (job.status === "succeeded" || job.status === "failed");

  useEffect(() => {
    if (!jobId) return;
    stopped.current = false;
    let active = true;
    let timer: ReturnType<typeof setInterval> | null = null;

    const fetchOnce = async () => {
      if (!active || stopped.current) return;
      try {
        const record = await api.getJob(jobId);
        if (!active) return;
        setJob(record);
        setError(null);
        if (record.status === "succeeded" || record.status === "failed") {
          stopped.current = true;
          if (timer) clearInterval(timer);
        }
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (active) setLoading(false);
      }
    };

    void fetchOnce();
    timer = setInterval(() => void fetchOnce(), POLL_MS);
    return () => {
      active = false;
      stopped.current = true;
      if (timer) clearInterval(timer);
    };
  }, [jobId]);

  return { job, error, loading, terminal };
}
