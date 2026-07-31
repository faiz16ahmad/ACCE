"use client";

import { useEffect, useState } from "react";

import { useJob } from "@/hooks/useJob";
import { useArtifacts } from "@/hooks/useArtifacts";
import { Tabs, type TabItem } from "@/components/ui/Tabs";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { StatusPill } from "@/components/jobs/StatusPill";
import { StagePipeline } from "@/components/jobs/StagePipeline";
import { LogViewer } from "@/components/logs/LogViewer";
import { VideoPreview } from "@/components/preview/VideoPreview";
import { ArtifactExplorer } from "@/components/artifacts/ArtifactExplorer";
import { QualityPanel } from "@/components/quality/QualityPanel";
import { formatClock } from "@/lib/format";
import { IconFilm, IconTerminal, IconAlert } from "@/components/ui/icons";

type TabKey = "progress" | "preview" | "artifacts" | "quality" | "logs";

function PendingPanel({ label }: { label: string }) {
  return (
    <EmptyState
      icon={<Spinner className="h-5 w-5 text-muted" />}
      title={`${label} will appear here`}
      description="The pipeline is still running. Head over to Progress to watch it build."
    />
  );
}

export function RunWorkspace({ jobId }: { jobId: string }) {
  const { job, error, loading, terminal } = useJob(jobId);
  const { artifacts, refresh: refreshArtifacts } = useArtifacts(jobId, terminal);
  const [tab, setTab] = useState<TabKey>("progress");

  const status = job?.status ?? "pending";
  const succeeded = status === "succeeded";
  const failed = status === "failed";
  const result = job?.result ?? null;

  // Auto-advance from Progress to Preview once the pipeline finishes.
  useEffect(() => {
    if (succeeded) setTab((current) => (current === "progress" ? "preview" : current));
  }, [succeeded]);

  // Refresh artifacts when the run just finished.
  useEffect(() => {
    if (succeeded) void refreshArtifacts();
  }, [succeeded, refreshArtifacts]);

  if (loading && !job) {
    return (
      <div className="flex h-full items-center justify-center gap-3 text-muted">
        <Spinner /> Loading run…
      </div>
    );
  }

  if (error && !job) {
    return (
      <EmptyState
        icon={<IconFilm />}
        title="Run not found"
        description={error}
        action={
          <Button variant="outline" onClick={() => window.history.back()}>
            Back
          </Button>
        }
      />
    );
  }

  if (!job) return null;

  const items: TabItem[] = [
    { key: "progress", label: "Progress" },
    { key: "preview", label: "Preview" },
    { key: "artifacts", label: "Artifacts" },
    {
      key: "quality",
      label: "Quality",
      badge: succeeded ? (
        <Badge tone="ok" className="px-1.5 py-0 text-[10px]">
          ✓
        </Badge>
      ) : undefined,
    },
    { key: "logs", label: "Logs", badge: <IconTerminal className="h-3 w-3 text-muted" /> },
  ];

  return (
    <div>
      <header className="mb-6 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="truncate text-xl font-semibold tracking-tight">
              {result?.input?.topic || "Untitled"}
            </h1>
            <StatusPill status={status} />
          </div>
          <p className="mt-1 truncate font-mono text-xs text-muted">
            {jobId}
            {result?.started_at ? ` · started ${formatClock(result.started_at)}` : ""}
            {result?.finished_at ? ` · finished ${formatClock(result.finished_at)}` : ""}
          </p>
        </div>
        {failed && job.error ? (
          <span className="flex items-center gap-1.5 text-xs text-danger">
            <IconAlert className="h-4 w-4" /> {job.error}
          </span>
        ) : null}
      </header>

      {failed ? (
        <div className="mb-6 rounded-lg border border-danger/25 bg-danger/10 px-4 py-3 text-sm text-danger">
          <strong>This run failed.</strong>{" "}
          {result?.errors?.join("; ") || job.error || "No details recorded."}
        </div>
      ) : null}

      <Tabs items={items} active={tab} onChange={(key) => setTab(key as TabKey)} />

      <div className="pt-6">
        {tab === "progress" && (
          <StagePipeline result={result} status={status} logs={job.logs} />
        )}
        {tab === "preview" &&
          (succeeded ? (
            <VideoPreview artifacts={artifacts} />
          ) : (
            <PendingPanel label="Your video preview" />
          ))}
        {tab === "artifacts" &&
          (terminal ? (
            <ArtifactExplorer jobId={jobId} artifacts={artifacts} />
          ) : (
            <PendingPanel label="Artifacts" />
          ))}
        {tab === "quality" &&
          (succeeded && result ? (
            <QualityPanel result={result} />
          ) : (
            <PendingPanel label="Quality report" />
          ))}
        {tab === "logs" && <LogViewer logs={job.logs} height="h-[420px]" />}
      </div>
    </div>
  );
}
