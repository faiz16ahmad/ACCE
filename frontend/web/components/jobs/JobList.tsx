"use client";

import Link from "next/link";

import { useJobs } from "@/hooks/useJobs";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { IconFilm, IconPlus } from "@/components/ui/icons";
import { JobCard } from "./JobCard";

export function JobList() {
  const { jobs, loading, error, refresh } = useJobs();

  if (error) {
    return (
      <EmptyState
        icon={<IconFilm />}
        title="Can't reach the API"
        description={error}
        action={
          <Button variant="outline" onClick={() => void refresh()}>
            Retry
          </Button>
        }
      />
    );
  }

  if (!loading && jobs.length === 0) {
    return (
      <EmptyState
        icon={<IconFilm />}
        title="No projects yet"
        description="Generate your first video — pick a topic and watch the pipeline build a narrated, illustrated video."
        action={
          <Link href="/generate">
            <Button>
              <IconPlus className="h-4 w-4" />
              New project
            </Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {loading && jobs.length === 0
        ? Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl border border-border bg-surface" />
          ))
        : jobs.map((job) => <JobCard key={job.job_id} job={job} />)}
    </div>
  );
}
