"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, artifactUrl, libraryTrackUrl } from "@/lib/api";
import type {
  DirectorSnapshotDto,
  DirectorStateDto,
  ExportRecordDto,
  MusicTrackDto,
} from "@/lib/types";
import { formatBytes } from "@/lib/format";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  IconAudio,
  IconCheck,
  IconDownload,
  IconLayers,
  IconPlay,
  IconRefresh,
  IconSparkle,
} from "@/components/ui/icons";

/* ────────────────────────────────────────────────────────────────── */
/*  Public entry                                                      */
/* ────────────────────────────────────────────────────────────────── */

export function DirectorMode({ jobId }: { jobId: string }) {
  const [snap, setSnap] = useState<DirectorSnapshotDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [exports, setExports] = useState<ExportRecordDto[]>([]);
  const [uploading, setUploading] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  /* --- fetch snapshot on mount --- */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [snapRes, exportsRes] = await Promise.all([
          api.getDirector(jobId),
          api.getDirectorExports(jobId),
        ]);
        if (cancelled) return;
        setSnap(snapRes);
        setExports(exportsRes.exports);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "Failed to load Director state");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  /* --- actions (each refreshes snapshot + exports) --- */
  const refresh = useCallback(async () => {
    const [snapRes, exportsRes] = await Promise.all([
      api.getDirector(jobId),
      api.getDirectorExports(jobId),
    ]);
    setSnap(snapRes);
    setExports(exportsRes.exports);
  }, [jobId]);

  const setMusic = useCallback(
    async (body: {
      mode: string;
      track_id?: string | null;
      volume?: number;
      fade_in?: number;
      fade_out?: number;
    }) => {
      setBusyAction("music");
      try {
        const res = await api.setDirectorMusic(jobId, body);
        setSnap((prev) => (prev ? { ...prev, state: res.state, current_track: res.current_track } : prev));
      } finally {
        setBusyAction(null);
      }
    },
    [jobId],
  );

  const doPreview = useCallback(async () => {
    setBusyAction("preview");
    try {
      const { preview_url } = await api.previewDirector(jobId);
      setPreviewUrl(preview_url);
    } finally {
      setBusyAction(null);
    }
  }, [jobId]);

  const doExport = useCallback(async () => {
    setBusyAction("export");
    try {
      const { export: rec } = await api.exportDirector(jobId);
      setExports((prev) => [rec, ...prev]);
    } finally {
      setBusyAction(null);
    }
  }, [jobId]);

  const doUpload = useCallback(
    async (file: File, name: string) => {
      setUploading(true);
      try {
        await api.uploadDirectorTrack(jobId, file, name);
        await refresh();
      } finally {
        setUploading(false);
        if (fileRef.current) fileRef.current.value = "";
      }
    },
    [jobId, refresh],
  );

  /* --- loading / error --- */
  if (loading) return <Spinner className="h-5 w-5 text-muted" />;
  if (error) return <EmptyState title="Director Mode unavailable" description={error} />;
  if (!snap) return <EmptyState title="No state" />;

  const { state, current_track: track, recommendations, library } = snap;
  const music = state.music;

  return (
    <Card className="overflow-visible">
      <CardHeader>
        <div className="flex items-center gap-2">
          <IconLayers className="h-4 w-4 text-accent" />
          <span className="text-sm font-semibold">Director Mode</span>
        </div>
        <span className="font-mono text-xs text-muted">
          {music.mode === "ai" ? "AI pick" : music.mode === "none" ? "narration only" : music.mode}
        </span>
      </CardHeader>

      <div className="flex flex-col gap-5 p-4">

        {/* ---------- current music ---------- */}
        <section>
          <h4 className="mb-2 text-xs font-medium uppercase text-muted">Current Music</h4>
          {music.mode === "none" ? (
            <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm text-muted">
              Narration only — no background music
            </div>
          ) : track ? (
            <CurrentMusic
              track={track}
              isAi={music.mode === "ai"}
              state={music}
              onSet={setMusic}
              onPreview={doPreview}
              onRevert={() => setMusic({ mode: "ai" })}
              onRemove={() => setMusic({ mode: "none" })}
              busy={busyAction === "music"}
            />
          ) : (
            <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm text-muted">
              Current track unresolvable — using original audio
            </div>
          )}
        </section>

        {/* ---------- recommendations ---------- */}
        {recommendations.length > 0 && (
          <section>
            <h4 className="mb-2 text-xs font-medium uppercase text-muted">
              Recommended for this run
            </h4>
            <div className="flex flex-col gap-2">
              {recommendations.map((t) => (
                <TrackRow
                  key={t.track_id}
                  track={t}
                  active={music.track_id === t.track_id}
                  onSelect={() =>
                    setMusic({ mode: "library", track_id: t.track_id, volume: music.volume })
                  }
                  busy={busyAction === "music"}
                />
              ))}
            </div>
          </section>
        )}

        {/* ---------- browse library ---------- */}
        <LibrarySection
          tracks={library}
          activeTrackId={music.track_id}
          onSelect={(trackId) =>
            setMusic({ mode: "library", track_id: trackId, volume: music.volume })
          }
          busy={busyAction === "music"}
        />

        {/* ---------- upload ---------- */}
        <UploadSection
          uploading={uploading}
          onUpload={doUpload}
          inputRef={fileRef}
        />

        {/* ---------- preview + export ---------- */}
        <section className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <Button
              variant="primary"
              size="sm"
              onClick={doPreview}
              disabled={busyAction !== null}
            >
              {busyAction === "preview" ? (
                <Spinner className="h-3.5 w-3.5" />
              ) : (
                <IconPlay className="h-3.5 w-3.5" />
              )}
              Preview
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={doExport}
              disabled={busyAction !== null}
            >
              {busyAction === "export" ? (
                <Spinner className="h-3.5 w-3.5" />
              ) : (
                <IconDownload className="h-3.5 w-3.5" />
              )}
              Export
            </Button>
          </div>

          {/* preview player */}
          {previewUrl && (
            <div className="rounded-lg border border-border bg-surface-1 p-3">
              <p className="mb-2 text-xs font-medium text-muted">Preview (baked mix)</p>
              <video
                key={previewUrl}
                src={artifactUrl(previewUrl)}
                controls
                className="w-full rounded"
              />
            </div>
          )}

          {/* exports history */}
          {exports.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-xs font-medium text-muted">Exports</p>
              {exports.map((ex) => (
                <div
                  key={ex.export_id}
                  className="flex items-center justify-between gap-2 rounded-md border border-border bg-surface-2 px-3 py-2 text-xs"
                >
                  <span className="truncate font-mono text-muted">{ex.export_id}</span>
                  <span className="text-muted">
                    {ex.duration.toFixed(0)}s · {formatBytes(ex.size)}
                  </span>
                  <a
                    href={artifactUrl(ex.url)}
                    download
                    className="text-accent hover:underline"
                  >
                    <IconDownload className="inline h-3.5 w-3.5" />
                  </a>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </Card>
  );
}

/* ────────────────────────────────────────────────────────────────── */
/*  Current music — volume/fades/mute (instant player + baked remix)   */
/* ────────────────────────────────────────────────────────────────── */

const MAX_FADE = 8; // seconds, mirrors ACCE_AUDIO__MUSIC_MAX_FADE

function CurrentMusic({
  track,
  isAi,
  state,
  onSet,
  onPreview,
  onRevert,
  onRemove,
  busy,
}: {
  track: MusicTrackDto;
  isAi: boolean;
  state: DirectorStateDto["music"];
  onSet: (body: { mode: string; volume?: number; fade_in?: number; fade_out?: number }) => void;
  onPreview: () => void;
  onRevert: () => void;
  onRemove: () => void;
  busy: boolean;
}) {
  const [vol, setVol] = useState(state.volume);
  const [fadeIn, setFadeIn] = useState(state.fade_in);
  const [fadeOut, setFadeOut] = useState(state.fade_out);
  const [muted, setMuted] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const commitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* keep player gain in sync with the slider — the user hears changes NOW */
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = muted ? 0 : vol;
      audioRef.current.muted = muted;
    }
  }, [vol, muted]);

  /* resync local state when the baked state changes (e.g. revert/swap) */
  useEffect(() => {
    setVol(state.volume);
    setFadeIn(state.fade_in);
    setFadeOut(state.fade_out);
  }, [state.volume, state.fade_in, state.fade_out]);

  const commit = useCallback(
    (v: number, fi: number, fo: number) => {
      onSet({ mode: state.mode, volume: v, fade_in: fi, fade_out: fo });
    },
    [onSet, state.mode],
  );

  /* called on release of any control: commit the final value + re-bake the mix */
  const release = useCallback(() => {
    if (commitTimer.current) clearTimeout(commitTimer.current);
    commit(vol, fadeIn, fadeOut);
    onPreview();
  }, [commit, vol, fadeIn, fadeOut, onPreview]);

  const src = libraryTrackUrl(track.track_id);

  return (
    <div className="rounded-lg border border-border bg-surface-1 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <IconAudio className="h-4 w-4 shrink-0 text-accent" />
          <span className="truncate text-sm font-medium">{track.title}</span>
          {isAi && (
            <span className="shrink-0 inline-flex items-center gap-1 rounded-md bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
              <IconSparkle className="h-3 w-3" /> AI
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setMuted((m) => !m)}
            disabled={busy}
            title={muted ? "Unmute" : "Mute"}
            className={`rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors ${
              muted
                ? "bg-danger/15 text-danger"
                : "text-muted hover:bg-surface-2 hover:text-foreground"
            }`}
          >
            {muted ? "MUTED" : "MUTE"}
          </button>
          {!isAi && (
            <button
              onClick={onRevert}
              disabled={busy}
              title="Revert to AI recommendation"
              className="rounded p-1 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              <IconRefresh className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={onRemove}
            disabled={busy}
            title="Remove music (narration only)"
            className="rounded p-1 text-muted transition-colors hover:bg-danger/15 hover:text-danger"
          >
            ×
          </button>
        </div>
      </div>

      <audio key={src} ref={audioRef} src={src} controls preload="metadata" className="w-full" />

      {/* volume */}
      <div className="mt-2 flex items-center gap-3">
        <span className="w-9 text-right text-xs font-mono text-muted">vol</span>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={vol}
          onChange={(e) => setVol(parseFloat(e.target.value))}
          onMouseUp={release}
          onKeyUp={release}
          className="h-1.5 flex-1 cursor-pointer appearance-none rounded bg-surface-2 accent-accent"
        />
        <span className="w-9 text-xs font-mono text-muted">{Math.round(vol * 100)}%</span>
      </div>

      {/* fades */}
      <div className="mt-2 flex items-center gap-3">
        <span className="w-9 text-right text-xs font-mono text-muted">fade</span>
        <div className="flex flex-1 items-center gap-2">
          <label className="flex flex-1 items-center gap-1.5 text-[10px] text-muted">
            in
            <input
              type="range"
              min="0"
              max={MAX_FADE}
              step="0.5"
              value={fadeIn}
              onChange={(e) => setFadeIn(parseFloat(e.target.value))}
              onMouseUp={release}
              onKeyUp={release}
              className="h-1 flex-1 cursor-pointer appearance-none rounded bg-surface-2 accent-accent"
            />
            <span className="w-7 font-mono">{fadeIn.toFixed(1)}s</span>
          </label>
          <label className="flex flex-1 items-center gap-1.5 text-[10px] text-muted">
            out
            <input
              type="range"
              min="0"
              max={MAX_FADE}
              step="0.5"
              value={fadeOut}
              onChange={(e) => setFadeOut(parseFloat(e.target.value))}
              onMouseUp={release}
              onKeyUp={release}
              className="h-1 flex-1 cursor-pointer appearance-none rounded bg-surface-2 accent-accent"
            />
            <span className="w-7 font-mono">{fadeOut.toFixed(1)}s</span>
          </label>
        </div>
      </div>

      {/* metadata chips */}
      <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-muted">
        <span>{track.provider}</span>
        {track.duration > 0 && <span>{track.duration.toFixed(0)}s</span>}
        {track.bpm && <span>{track.bpm}bpm</span>}
        {track.license && <span>{track.license}</span>}
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────── */
/*  Library rows + upload with name                                   */
/* ────────────────────────────────────────────────────────────────── */

function TrackRow({
  track,
  active,
  onSelect,
  busy,
}: {
  track: MusicTrackDto;
  active: boolean;
  onSelect: () => void;
  busy: boolean;
}) {
  const src = libraryTrackUrl(track.track_id);
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs transition-colors hover:border-accent/30">
      <audio preload="none" controls className="h-7 w-44 min-w-0 flex-shrink" src={src} />
      <span className="truncate font-medium min-w-0 flex-1">{track.title}</span>
      <span className="text-muted">{track.duration.toFixed(0)}s</span>
      <span className="text-muted">{track.provider}</span>
      <Button
        variant={active ? "primary" : "ghost"}
        size="sm"
        onClick={onSelect}
        disabled={busy || active}
      >
        {active ? <IconCheck className="h-3 w-3" /> : <IconPlay className="h-3 w-3" />}
        {active ? "Selected" : "Use"}
      </Button>
    </div>
  );
}

function LibrarySection({
  tracks,
  activeTrackId,
  onSelect,
  busy,
}: {
  tracks: MusicTrackDto[];
  activeTrackId?: string | null;
  onSelect: (trackId: string) => void;
  busy: boolean;
}) {
  const [q, setQ] = useState("");
  const [filtered, setFiltered] = useState(tracks);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!q.trim()) {
      setFiltered(tracks);
      return;
    }
    const qLower = q.toLowerCase();
    setFiltered(tracks.filter((t) => t.title.toLowerCase().includes(qLower)));
  }, [tracks, q]);

  const serverRefetch = useCallback(async () => {
    if (!q.trim()) {
      setFiltered(tracks);
      return;
    }
    setLoading(true);
    try {
      const { tracks: result } = await api.getMusicLibrary(q);
      setFiltered(result);
    } finally {
      setLoading(false);
    }
  }, [q, tracks]);

  useEffect(() => {
    const t = setTimeout(serverRefetch, 250);
    return () => clearTimeout(t);
  }, [serverRefetch]);

  return (
    <section>
      <h4 className="mb-2 text-xs font-medium uppercase text-muted">Library</h4>
      <input
        type="text"
        placeholder="Search tracks…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="mb-2 w-full rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-xs text-foreground placeholder:text-muted/60 focus:outline-none focus:ring-1 focus:ring-accent/40"
      />
      {loading && <Spinner className="mb-2 h-4 w-4 text-muted" />}
      <div className="flex max-h-[260px] flex-col gap-1.5 overflow-y-auto pr-1">
        {filtered.length === 0 && <p className="py-3 text-center text-xs text-muted">No tracks</p>}
        {filtered.map((track) => (
          <TrackRow
            key={track.track_id}
            track={track}
            active={activeTrackId === track.track_id}
            onSelect={() => onSelect(track.track_id)}
            busy={busy}
          />
        ))}
      </div>
    </section>
  );
}

function UploadSection({
  uploading,
  onUpload,
  inputRef,
}: {
  uploading: boolean;
  onUpload: (file: File, name: string) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  const [pending, setPending] = useState<File | null>(null);
  const [name, setName] = useState("");

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPending(file);
    setName(file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " "));
  };

  const cancel = () => {
    setPending(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <section>
      <h4 className="mb-2 text-xs font-medium uppercase text-muted">Upload to Library</h4>

      {pending ? (
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface-2 p-3">
          <p className="text-xs text-muted">
            Uploading <span className="font-medium text-foreground">{pending.name}</span>
          </p>
          <label className="flex items-center gap-2 text-xs">
            <span className="text-muted">Name it (genre / BGM title)</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Space Documentary"
              className="flex-1 rounded-md border border-border bg-surface-1 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-accent/40"
            />
          </label>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={() => onUpload(pending, name)}
              disabled={uploading || !name.trim()}
            >
              {uploading ? <Spinner className="h-3.5 w-3.5" /> : <IconCheck className="h-3.5 w-3.5" />}
              Add to Library
            </Button>
            <Button variant="ghost" size="sm" onClick={cancel} disabled={uploading}>
              Cancel
            </Button>
            <span className="text-[10px] text-muted">Available to every project</span>
          </div>
        </div>
      ) : (
        <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-surface-2 p-4 text-xs text-muted transition-colors hover:border-accent/60 hover:text-muted/80">
          <input
            ref={inputRef}
            type="file"
            accept=".mp3,.wav,.ogg,.m4a,.flac"
            className="hidden"
            onChange={handleFile}
          />
          <IconLayers className="h-4 w-4" />
          <span>Click to browse (MP3 / WAV) — goes to your global music library</span>
        </label>
      )}
    </section>
  );
}
