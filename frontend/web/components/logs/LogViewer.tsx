"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Input } from "@/components/ui/Field";
import { cn } from "@/lib/cn";

const STATUS_COLORS: Record<string, string> = {
  started: "text-warn",
  succeeded: "text-ok",
  failed: "text-danger",
  retrying: "text-warn",
};

function LogLine({ line }: { line: string }) {
  const match = line.match(/^\[([a-z_]+)\] (started|succeeded|failed|retrying): (.*)$/);
  if (!match) return <div className="whitespace-pre-wrap break-words">{line}</div>;
  const [, stage, status, message] = match;
  return (
    <div className="whitespace-pre-wrap break-words">
      <span className="text-accent">[{stage}]</span>{" "}
      <span className={STATUS_COLORS[status] ?? "text-zinc-300"}>{status}</span>
      <span className="text-zinc-400">: {message}</span>
    </div>
  );
}

export function LogViewer({ logs, height = "h-64" }: { logs: string[]; height?: string }) {
  const [filter, setFilter] = useState("");
  const [pinned, setPinned] = useState(true);
  const ref = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    if (!filter) return logs;
    const needle = filter.toLowerCase();
    return logs.filter((line) => line.toLowerCase().includes(needle));
  }, [logs, filter]);

  useEffect(() => {
    if (pinned && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [filtered, pinned]);

  return (
    <div>
      <div className="mb-2 flex items-center gap-3">
        <Input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter logs…"
          className="h-8 max-w-xs text-xs"
        />
        <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted">
          <input
            type="checkbox"
            checked={pinned}
            onChange={(event) => setPinned(event.target.checked)}
          />
          Auto-scroll
        </label>
      </div>
      <div
        ref={ref}
        onScroll={(event) => {
          const el = event.currentTarget;
          setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 40);
        }}
        className={cn(
          "overflow-y-auto rounded-lg border border-border bg-[#0a0c10] p-3 font-mono text-xs leading-relaxed text-zinc-300",
          height,
        )}
      >
        {filtered.length === 0 ? (
          <p className="text-zinc-500">No logs yet…</p>
        ) : (
          filtered.map((line, index) => <LogLine key={index} line={line} />)
        )}
      </div>
    </div>
  );
}
