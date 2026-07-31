import Link from "next/link";

import type { JobSummary } from "@/lib/types";
import { artifactUrl } from "@/lib/api";
import { formatClock } from "@/lib/format";
import { Card, CardBody } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { IconChevronRight, IconFilm } from "@/components/ui/icons";
import { StatusPill } from "./StatusPill";

function ScoreBadge({ score }: { score?: number | null }) {
  if (score == null) return null;
  const tone = score >= 80 ? "ok" : score >= 50 ? "warn" : "danger";
  return <Badge tone={tone}>{score} score</Badge>;
}

export function JobCard({ job }: { job: JobSummary }) {
  return (
    <Link href={`/runs/${job.job_id}`} className="group block">
      <Card className="transition-colors hover:border-accent/40 hover:bg-surface-2/40">
        <CardBody className="flex items-center gap-4 p-4">
          {job.thumbnail ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={artifactUrl(job.thumbnail)}
              alt={`Poster for ${job.topic || job.job_id}`}
              className="h-14 w-24 shrink-0 rounded-lg border border-border object-cover"
            />
          ) : (
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted group-hover:text-accent">
              <IconFilm className="h-5 w-5" />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-sm font-semibold">{job.topic || job.job_id}</h3>
              <StatusPill status={job.status} />
            </div>
            <p className="mt-0.5 truncate font-mono text-xs text-muted">
              {job.job_id} · {formatClock(job.created_at)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <ScoreBadge score={job.score} />
            <IconChevronRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5" />
          </div>
        </CardBody>
      </Card>
    </Link>
  );
}
