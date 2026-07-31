"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface TabItem {
  key: string;
  label: string;
  badge?: ReactNode;
}

export function Tabs({
  items,
  active,
  onChange,
}: {
  items: TabItem[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-border">
      {items.map((item) => {
        const selected = item.key === active;
        return (
          <button
            key={item.key}
            onClick={() => onChange(item.key)}
            className={cn(
              "relative -mb-px flex items-center gap-1.5 whitespace-nowrap px-4 py-2.5 text-sm transition-colors",
              selected ? "text-foreground" : "text-muted hover:text-foreground",
            )}
          >
            {item.label}
            {item.badge}
            {selected ? (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent" />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
