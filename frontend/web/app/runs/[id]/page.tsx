import type { Metadata } from "next";

import { RunWorkspace } from "@/components/runs/RunWorkspace";

export const metadata: Metadata = { title: "Run — ACCE Studio" };

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <RunWorkspace jobId={id} />;
}
