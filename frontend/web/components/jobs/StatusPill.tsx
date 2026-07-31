import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/cn";

type Tone = "neutral" | "ok" | "warn" | "danger" | "accent";

const TONE: Record<string, Tone> = {
  succeeded: "ok",
  running: "accent",
  pending: "neutral",
  failed: "danger",
};

export function StatusPill({ status, className }: { status: string; className?: string }) {
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  return (
    <Badge tone={TONE[status] ?? "neutral"} className={cn("capitalize", className)}>
      {status === "running" && <Spinner className="h-3 w-3" />}
      {label}
    </Badge>
  );
}
