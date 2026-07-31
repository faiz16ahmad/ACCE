/** Small pure formatting helpers (unit-tested). */

import { STAGE_LABELS } from "./types";

/** Extract the progress percent from an orchestrator log line, if present. */
export function parsePercent(logLine: string): number | null {
  const match = logLine.match(/(\d+(?:\.\d+)?)%/);
  return match ? Math.round(parseFloat(match[1])) : null;
}

/** Last percent seen across a list of log lines (fallback when no live field). */
export function latestPercent(logs: string[]): number | null {
  let latest: number | null = null;
  for (const line of logs) {
    const pct = parsePercent(line);
    if (pct !== null) latest = pct;
  }
  return latest;
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function formatClock(epochSec: number | null | undefined): string {
  if (!epochSec) return "—";
  return new Date(epochSec * 1000).toLocaleString();
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}
