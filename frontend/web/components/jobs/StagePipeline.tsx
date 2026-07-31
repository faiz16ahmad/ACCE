"use client";

import { STAGES, STAGE_LABELS, type JobSnapshot } from "@/lib/types";
import { formatDuration, latestPercent } from "@/lib/format";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Spinner } from "@/components/ui/Spinner";
import { IconCheck, IconX } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

export function StagePipeline({
  result,
  status,
  logs,
}: {
  result: JobSnapshot | null;
  status: string;
  logs: string[];
}) {
  const results = result?.results ?? {};
  const current = result?.current_stage ?? null;
  const percent = latestPercent(logs);
  const running = status === "running" || status === "pending";

  const progress =
    status === "succeeded" || status === "failed" ? 100 : percent ?? 0;

  return (
    <div>
      <div className="mb-5 flex items-center gap-3">
        <ProgressBar
          value={progress}
          indeterminate={running && percent == null}
          className="flex-1"
        />
        <span className="w-14 text-right font-mono text-xs text-muted">
          {percent != null ? `${percent}%` : status}
        </span>
      </div>

      <ol className="divide-y divide-border/50 rounded-lg border border-border bg-surface">
        {STAGES.map((stage) => {
          const res = results[stage];
          const done = res?.ok === true;
          const failed = res?.ok === false;
          const active = stage === current;
          return (
            <li key={stage} className="flex items-center gap-3 px-4 py-2.5">
              <span
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                  done
                    ? "bg-ok/15 text-ok"
                    : failed
                      ? "bg-danger/15 text-danger"
                      : active
                        ? "bg-accent/15 text-accent"
                        : "bg-surface-2 text-muted",
                )}
              >
                {done ? (
                  <IconCheck className="h-3 w-3" />
                ) : failed ? (
                  <IconX className="h-3 w-3" />
                ) : active ? (
                  <Spinner className="h-3 w-3" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                )}
              </span>
              <span
                className={cn(
                  "flex-1 text-sm",
                  done || failed || active ? "text-foreground" : "text-muted",
                )}
              >
                {STAGE_LABELS[stage] ?? stage}
              </span>
              {failed && res?.error ? (
                <span className="truncate font-mono text-xs text-danger" title={res.error}>
                  {res.error.split(":")[0]}
                </span>
              ) : null}
              {res?.duration_ms ? (
                <span className="font-mono text-xs text-muted">
                  {formatDuration(res.duration_ms)}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
