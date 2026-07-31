import type { Metadata } from "next";

import { GenerateForm } from "@/components/generate/GenerateForm";

export const metadata: Metadata = { title: "Generate — ACCE Studio" };

export default function GeneratePage() {
  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">New project</h1>
        <p className="mt-1 text-sm text-muted">
          Give ACCE a topic. Research, script, visuals, narration, music, and
          render are generated automatically.
        </p>
      </header>
      <GenerateForm />
    </div>
  );
}
