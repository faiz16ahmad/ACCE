"use client";

import { useState } from "react";

import { artifactUrl } from "@/lib/api";
import type { ArtifactDto } from "@/lib/types";
import { formatBytes } from "@/lib/format";
import { EmptyState } from "@/components/ui/EmptyState";
import { IconDownload, IconFilm } from "@/components/ui/icons";

export function VideoPreview({ artifacts }: { artifacts: ArtifactDto[] }) {
  const [playbackError, setPlaybackError] = useState(false);

  const video =
    artifacts.find(
      (asset) =>
        asset.name === "final_video.mp4" || asset.mime.startsWith("video/"),
    ) ?? null;

  const thumbnail =
    artifacts.find((asset) => asset.name === "thumbnail.jpg") ?? null;

  if (!video) {
    return (
      <EmptyState
        icon={<IconFilm />}
        title="No rendered video"
        description="The Production stage did not produce a playable file."
      />
    );
  }

  const src = artifactUrl(video.url);
  const poster = thumbnail ? artifactUrl(thumbnail.url) : undefined;

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-xl border border-border bg-black">
        {playbackError ? (
          <div className="flex aspect-video w-full items-center justify-center px-6 text-center text-sm text-muted">
            This render is a stub placeholder. Enable a real renderer (FFmpeg)
            and media providers to preview the actual video.
          </div>
        ) : (
          <video
            key={src}
            src={src}
            poster={poster}
            controls
            playsInline
            className="aspect-video w-full"
            onError={() => setPlaybackError(true)}
          />
        )}
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="truncate text-sm text-muted">
          <span className="font-mono">{video.name}</span> · {formatBytes(video.size)}
        </p>
        <div className="flex shrink-0 items-center gap-2">
          {thumbnail ? (
            <a
              href={poster}
              download
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-border px-3 text-sm font-medium transition-colors hover:bg-surface-2"
            >
              <IconDownload className="h-4 w-4" />
              Thumbnail
            </a>
          ) : null}
          <a
            href={src}
            download
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-border px-4 text-sm font-medium transition-colors hover:bg-surface-2"
          >
            <IconDownload className="h-4 w-4" />
            Download
          </a>
        </div>
      </div>
    </div>
  );
}
