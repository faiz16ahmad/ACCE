"use client";

import type { JobSnapshot, QualityIssueDto, QualityReportDto } from "@/lib/types";
import { stageLabel } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { IconCheck } from "@/components/ui/icons";

const LEVEL_TONE: Record<string, "neutral" | "ok" | "warn" | "danger"> = {
  info: "neutral",
  warning: "warn",
  error: "danger",
};

function ScoreGauge({ score }: { score: number }) {
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100);
  const color = score >= 80 ? "var(--ok)" : score >= 50 ? "var(--warn)" : "var(--danger)";

  return (
    <Card>
      <CardBody className="flex flex-col items-center gap-2 p-5">
        <svg width="92" height="92" viewBox="0 0 80 80">
          <circle cx="40" cy="40" r={radius} fill="none" stroke="var(--surface-2)" strokeWidth="7" />
          <circle
            cx="40"
            cy="40"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            transform="rotate(-90 40 40)"
          />
          <text
            x="40"
            y="46"
            textAnchor="middle"
            className="fill-foreground"
            fontSize="19"
            fontWeight="700"
          >
            {Math.round(score)}
          </text>
        </svg>
        <p className="text-xs text-muted">Quality score</p>
      </CardBody>
    </Card>
  );
}

function MetricTile({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardBody className="flex flex-col gap-1 p-5">
        <span className="text-2xl font-semibold tracking-tight text-foreground">{value}</span>
        <span className="text-xs text-muted">{label}</span>
      </CardBody>
    </Card>
  );
}

function IssueRow({ issue }: { issue: QualityIssueDto }) {
  return (
    <div className="flex items-start gap-3 border-b border-border/50 px-4 py-3 last:border-0">
      <Badge tone={LEVEL_TONE[issue.level] ?? "neutral"} className="mt-0.5 shrink-0 capitalize">
        {issue.level}
      </Badge>
      <div className="min-w-0 flex-1">
        <p className="text-sm">{issue.message}</p>
        <p className="mt-0.5 font-mono text-[11px] text-muted">{issue.code}</p>
        {issue.suggested_fix ? (
          <p className="mt-1 text-xs italic text-muted">{issue.suggested_fix}</p>
        ) : null}
      </div>
      <span className="shrink-0 text-xs text-muted">{stageLabel(issue.stage)}</span>
    </div>
  );
}

export function QualityPanel({ result }: { result: JobSnapshot }) {
  const raw = result.results.quality?.output;
  if (!raw || typeof raw !== "object") {
    return (
      <EmptyState
        icon={<IconCheck />}
        title="No quality report"
        description="The Quality stage did not produce a report for this run."
      />
    );
  }
  const report = raw as unknown as QualityReportDto;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-4">
        <ScoreGauge score={report.score} />
        <MetricTile label="Warnings" value={report.warnings} />
        <MetricTile label="Errors" value={report.errors} />
        <MetricTile label="Issues" value={report.issues.length} />
      </div>

      {report.recommended_retry_stage ? (
        <Card className="border-warn/30">
          <CardHeader>
            <CardTitle>Recommended retry</CardTitle>
            <Badge tone="warn">{stageLabel(report.recommended_retry_stage)}</Badge>
          </CardHeader>
          <CardBody>
            <p className="text-sm text-muted">
              Re-run the <span className="font-medium text-foreground">{stageLabel(report.recommended_retry_stage)}</span>{" "}
              stage to address the blocking errors. This is a recommendation —
              retries are executed by the orchestrator, not the Quality stage.
            </p>
          </CardBody>
        </Card>
      ) : report.passed ? (
        <Card className="border-ok/30">
          <CardBody className="flex items-center gap-2 text-sm text-ok">
            <IconCheck className="h-4 w-4" />
            This run is ready to ship — no blocking errors.
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Issues ({report.issues.length})</CardTitle>
        </CardHeader>
        <div>
          {report.issues.length === 0 ? (
            <CardBody>
              <p className="text-sm text-muted">No issues detected.</p>
            </CardBody>
          ) : (
            report.issues.map((issue, index) => <IssueRow key={index} issue={issue} />)
          )}
        </div>
      </Card>
    </div>
  );
}
