"use client";

import { artifactUrl } from "@/lib/api";
import type { ArtifactDto } from "@/lib/types";
import { formatBytes } from "@/lib/format";
import { EmptyState } from "@/components/ui/EmptyState";
import { IconAudio, IconDownload } from "@/components/ui/icons";

const AUDIO_MIMES = /^(audio\/|application\/ogg)/;

export function AudioPreview({ artifacts }: { artifacts: ArtifactDto[] }) {
  const audioFiles = artifacts.filter((a) => AUDIO_MIMES.test(a.mime));

  if (!audioFiles.length) {
    return (
      <EmptyState
        icon={<IconAudio />}
        title="No audio files"
        description="The Audio stage did not produce any playable files."
      />
    );
  }

  // Master mix is the featured player; individual narrations listed below.
  const master = audioFiles.find((a) => a.name === "master_audio.m4a") ?? null;
  const narrations = audioFiles.filter(
    (a) => a !== master && a.name.startsWith("narration_"),
  );
  const others = audioFiles.filter(
    (a) => a !== master && !a.name.startsWith("narration_"),
  );

  return (
    <div className="flex flex-col gap-6">
      {master && <FeaturedAudio track={master} label="Master Mix" />}

      {narrations.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-medium text-muted">
            Scene Narrations
          </h3>
          <div className="flex flex-col gap-2">
            {narrations.map((track) => (
              <AudioRow key={track.path} track={track} />
            ))}
          </div>
        </section>
      )}

      {others.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-medium text-muted">
            Other Audio
          </h3>
          <div className="flex flex-col gap-2">
            {others.map((track) => (
              <AudioRow key={track.path} track={track} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Featured audio — large player for the master mix                   */
/* ------------------------------------------------------------------ */

function FeaturedAudio({ track, label }: { track: ArtifactDto; label: string }) {
  const src = artifactUrl(track.url);
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface-1 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <IconAudio className="h-4 w-4 text-accent" />
          <span className="text-sm font-medium">{label}</span>
        </div>
        <span className="font-mono text-xs text-muted">
          {track.name} · {formatBytes(track.size)}
        </span>
      </div>
      <audio
        key={src}
        src={src}
        controls
        preload="metadata"
        className="w-full"
      />
      <div className="mt-3 flex justify-end">
        <a
          href={src}
          download
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-medium transition-colors hover:bg-surface-2"
        >
          <IconDownload className="h-3.5 w-3.5" />
          Download
        </a>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Audio row — compact row for individual narration clips             */
/* ------------------------------------------------------------------ */

function AudioRow({ track }: { track: ArtifactDto }) {
  const src = artifactUrl(track.url);
  // Extract scene label from "narration_scene_01.mp3" → "Scene 1"
  const sceneMatch = track.name.match(/scene_(\d+)/);
  const label = sceneMatch ? `Scene ${parseInt(sceneMatch[1], 10)}` : track.name;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-surface-1 px-3 py-2">
      <span className="shrink-0 text-xs font-medium text-muted">
        {label}
      </span>
      <audio
        key={src}
        src={src}
        controls
        preload="metadata"
        className="min-w-0 flex-1"
      />
      <a
        href={src}
        download
        title={`Download ${track.name}`}
        className="shrink-0 inline-flex h-7 w-7 items-center justify-center rounded-md border border-border transition-colors hover:bg-surface-2"
      >
        <IconDownload className="h-3.5 w-3.5" />
      </a>
    </div>
  );
}
