"use client";

import type { ReactNode } from "react";

import { Sidebar } from "./Sidebar";

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full min-h-screen w-full">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl px-6 py-8 md:px-10">{children}</div>
      </main>
    </div>
  );
}
