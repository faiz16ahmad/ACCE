"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import type { LanguageDto } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import { IconSparkle } from "@/components/ui/icons";

const DURATIONS = [60, 120, 180, 240];
const STYLES = ["explainer", "educational", "storytelling", "news", "documentary", "top10"];

export function GenerateForm() {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [duration, setDuration] = useState<number>(120);
  const [style, setStyle] = useState("explainer");
  const [instructions, setInstructions] = useState("");
  const [language, setLanguage] = useState("en");
  const [languages, setLanguages] = useState<LanguageDto[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getLanguages()
      .then(({ languages }) => setLanguages(languages))
      .catch(() => {
        /* backend not up yet — the form still works with the default pick */
      });
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!topic.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const { job_id } = await api.createJob({
        topic: topic.trim(),
        duration,
        style,
        language,
        instructions: instructions
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
      });
      router.push(`/runs/${job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardBody className="p-6">
        <form onSubmit={onSubmit} className="flex flex-col gap-5">
          <Field label="Topic" htmlFor="topic" hint="What should the video be about?">
            <Input
              id="topic"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="e.g. How neural networks learn"
              autoFocus
            />
          </Field>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Target duration" htmlFor="duration">
              <Select
                id="duration"
                value={String(duration)}
                onChange={(event) => setDuration(Number(event.target.value))}
              >
                {DURATIONS.map((seconds) => (
                  <option key={seconds} value={seconds}>
                    {seconds >= 60 ? `${seconds / 60} min` : `${seconds}s`}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Style" htmlFor="style">
              <Select
                id="style"
                value={style}
                onChange={(event) => setStyle(event.target.value)}
              >
                {STYLES.map((value) => (
                  <option key={value} value={value}>
                    {value.charAt(0).toUpperCase() + value.slice(1)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field
            label="Language"
            htmlFor="language"
            hint="The narration and subtitles are produced in this language. Visuals stay English."
          >
            <Select
              id="language"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
            >
              {languages.length === 0 ? (
                <option value="en">English</option>
              ) : (
                languages.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.native_name} — {lang.english_name}
                  </option>
                ))
              )}
            </Select>
          </Field>

          <Field
            label="Instructions"
            htmlFor="instructions"
            hint="One per line. Optional guidance the pipeline should follow."
          >
            <Textarea
              id="instructions"
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              placeholder={"keep it beginner friendly\nmention real-world examples"}
            />
          </Field>

          {error ? (
            <p className="rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          ) : null}

          <div className="flex justify-end">
            <Button type="submit" size="lg" disabled={!topic.trim() || submitting}>
              {submitting ? (
                <Spinner className="h-4 w-4" />
              ) : (
                <IconSparkle className="h-4 w-4" />
              )}
              {submitting ? "Starting…" : "Generate video"}
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
