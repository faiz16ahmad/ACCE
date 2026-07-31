"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { ArtifactDto } from "@/lib/types";

export function useArtifacts(jobId: string | null, enabled: boolean) {
  const [artifacts, setArtifacts] = useState<ArtifactDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    try {
      const { artifacts } = await api.getArtifacts(jobId);
      setArtifacts(artifacts);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    if (!enabled) return;
    void refresh();
  }, [enabled, refresh]);

  return { artifacts, error, loading, refresh };
}
