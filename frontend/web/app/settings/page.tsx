"use client";

import { useState } from "react";

import { useApp } from "@/store/AppContext";
import { api } from "@/lib/api";
import type { HealthDto } from "@/lib/types";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";

export default function SettingsPage() {
  const { theme, toggleTheme, apiBase, updateApiBase } = useApp();
  const [base, setBase] = useState(apiBase);
  const [health, setHealth] = useState<HealthDto | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function check() {
    updateApiBase(base);
    setChecking(true);
    setError(null);
    try {
      const result = await api.health();
      setHealth(result);
    } catch (err) {
      setHealth(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted">
          Connection and appearance preferences for ACCE Studio.
        </p>
      </header>

      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Appearance</CardTitle>
          </CardHeader>
          <CardBody className="flex items-center justify-between">
            <p className="text-sm text-muted">
              Currently in <span className="font-medium text-foreground capitalize">{theme}</span> mode
            </p>
            <Button variant="outline" size="sm" onClick={toggleTheme}>
              Switch to {theme === "dark" ? "light" : "dark"}
            </Button>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>API connection</CardTitle>
            <Badge tone={health ? "ok" : error ? "danger" : "neutral"}>
              {health ? "connected" : error ? "unreachable" : "not checked"}
            </Badge>
          </CardHeader>
          <CardBody className="flex flex-col gap-4">
            <Field label="API base URL" hint="Where the ACCE FastAPI backend is running.">
              <Input
                value={base}
                onChange={(event) => setBase(event.target.value)}
                placeholder="http://127.0.0.1:8000"
              />
            </Field>
            <div className="flex items-center justify-between gap-3">
              {health ? (
                <p className="text-xs text-muted">
                  {health.app} v{health.version} · status {health.status}
                </p>
              ) : error ? (
                <p className="text-xs text-danger">{error}</p>
              ) : (
                <p className="text-xs text-muted">Test the connection to the backend.</p>
              )}
              <Button size="sm" onClick={() => void check()} disabled={checking || !base.trim()}>
                {checking ? "Checking…" : "Test connection"}
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
