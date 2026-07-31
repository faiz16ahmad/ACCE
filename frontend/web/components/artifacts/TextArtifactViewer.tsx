"use client";

import { useEffect, useState } from "react";

import { artifactUrl } from "@/lib/api";
import type { ArtifactDto } from "@/lib/types";
import { formatBytes } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { IconDownload } from "@/components/ui/icons";

/** Renders a JSON/text artifact, auto-detecting JSON for pretty-printing. */
export function TextArtifactViewer({ artifact }: { artifact: ArtifactDto }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setText(null);
    setError(null);
    fetch(artifactUrl(artifact.url))
      .then((res) => (res.ok ? res.text() : Promise.reject(new Error(`${res.status}`))))
      .then((body) => {
        if (!cancelled) setText(body);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [artifact.url]);

  if (error) return <p className="text-sm text-danger">Couldn&apos;t load artifact: {error}</p>;
  if (text === null) return <p className="text-sm text-muted">Loading…</p>;

  let pretty = text;
  try {
    pretty = JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    /* not JSON — show raw */
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="truncate font-mono text-xs text-muted">
          {artifact.name} · {formatBytes(artifact.size)}
        </p>
        <a href={artifactUrl(artifact.url)} download>
          <Button variant="outline" size="sm">
            <IconDownload className="h-3.5 w-3.5" />
            Download
          </Button>
        </a>
      </div>
      <pre className="max-h-[560px] overflow-auto rounded-lg border border-border bg-[#0a0c10] p-4 font-mono text-xs leading-relaxed text-zinc-300">
        {pretty}
      </pre>
    </div>
  );
}
