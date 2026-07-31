"use client";

import { useMemo, useState } from "react";

import { artifactUrl } from "@/lib/api";
import { STAGES, type ArtifactDto } from "@/lib/types";
import { formatBytes, stageLabel } from "@/lib/format";
import { cn } from "@/lib/cn";
import { IconFile } from "@/components/ui/icons";
import { EmptyState } from "@/components/ui/EmptyState";
import { TextArtifactViewer } from "./TextArtifactViewer";

const STAGE_ORDER = [...STAGES, "meta", "other"];

function ArtifactViewer({ artifact }: { artifact: ArtifactDto }) {
  const src = artifactUrl(artifact.url);
  if (artifact.mime.startsWith("image/")) {
    return (
      <div className="overflow-hidden rounded-lg border border-border bg-black">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={artifact.name} className="max-h-[560px] w-full object-contain" />
      </div>
    );
  }
  if (artifact.mime.startsWith("video/")) {
    return (
      <video src={src} controls className="max-h-[560px] w-full rounded-lg border border-border bg-black" />
    );
  }
  if (artifact.mime.includes("json") || artifact.mime.startsWith("text/")) {
    return <TextArtifactViewer artifact={artifact} />;
  }
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-surface p-10">
      <p className="text-sm text-muted">Binary artifact — download to inspect.</p>
      <a href={src} download>
        <span className="inline-flex h-9 items-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-on-accent">
          Download {artifact.name}
        </span>
      </a>
    </div>
  );
}

export function ArtifactExplorer({
  artifacts,
}: {
  jobId: string;
  artifacts: ArtifactDto[];
}) {
  const [selected, setSelected] = useState<ArtifactDto | null>(null);

  const groups = useMemo(() => {
    const map = new Map<string, ArtifactDto[]>();
    for (const artifact of artifacts) {
      const key = STAGE_ORDER.includes(artifact.stage) ? artifact.stage : "other";
      map.set(key, [...(map.get(key) ?? []), artifact]);
    }
    return [...map.entries()].sort(
      ([a], [b]) => STAGE_ORDER.indexOf(a) - STAGE_ORDER.indexOf(b),
    );
  }, [artifacts]);

  if (artifacts.length === 0) {
    return (
      <EmptyState
        icon={<IconFile />}
        title="No artifacts found"
        description="Nothing was written to this job directory."
      />
    );
  }

  const active = selected ?? artifacts[0];

  return (
    <div className="grid gap-4 md:grid-cols-[260px_1fr]">
      <nav className="flex max-h-[600px] flex-col gap-4 overflow-y-auto rounded-xl border border-border bg-surface p-3">
        {groups.map(([stage, files]) => (
          <div key={stage}>
            <p className="mb-1 px-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
              {stageLabel(stage)}
            </p>
            <ul className="flex flex-col gap-0.5">
              {files.map((file) => (
                <li key={file.path}>
                  <button
                    onClick={() => setSelected(file)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-1.5 py-1.5 text-left text-xs transition-colors",
                      active.path === file.path
                        ? "bg-accent/15 text-foreground"
                        : "text-muted hover:bg-surface-2 hover:text-foreground",
                    )}
                  >
                    <IconFile className="h-3.5 w-3.5 shrink-0" />
                    <span className="min-w-0 flex-1 truncate">{file.name}</span>
                    <span className="shrink-0 font-mono text-[10px] text-muted/70">
                      {formatBytes(file.size)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="min-w-0">
        <ArtifactViewer key={active.path} artifact={active} />
      </div>
    </div>
  );
}
