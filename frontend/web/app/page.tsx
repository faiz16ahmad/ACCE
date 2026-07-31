import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { IconPlus } from "@/components/ui/icons";
import { JobList } from "@/components/jobs/JobList";

export default function HomePage() {
  return (
    <div>
      <header className="mb-8 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-muted">
            Every video you&apos;ve generated with ACCE.
          </p>
        </div>
        <Link href="/generate">
          <Button>
            <IconPlus className="h-4 w-4" />
            New project
          </Button>
        </Link>
      </header>
      <JobList />
    </div>
  );
}
