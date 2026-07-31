import { describe, expect, it } from "vitest";

import { formatBytes, formatDuration, latestPercent, parsePercent } from "./format";

describe("parsePercent", () => {
  it("extracts the percent from an orchestrator log line", () => {
    expect(parsePercent("[scenes] succeeded: ok (42.9%)")).toBe(43);
    expect(parsePercent("[research] started: job x started (0.0%)")).toBe(0);
  });

  it("returns null when no percent is present", () => {
    expect(parsePercent("[script] succeeded: ok")).toBeNull();
    expect(parsePercent("no numbers here")).toBeNull();
  });
});

describe("latestPercent", () => {
  it("returns the last percent seen", () => {
    expect(
      latestPercent([
        "[research] succeeded: ok (14.3%)",
        "[scenes] started: running",
        "[scenes] succeeded: ok (42.9%)",
      ]),
    ).toBe(43);
  });

  it("returns null for an empty / percent-less stream", () => {
    expect(latestPercent([])).toBeNull();
    expect(latestPercent(["[script] failed: boom"])).toBeNull();
  });
});

describe("formatBytes", () => {
  it("formats sizes", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1048576)).toBe("1.0 MB");
  });
});

describe("formatDuration", () => {
  it("formats durations", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(45_000)).toBe("45s");
    expect(formatDuration(90_000)).toBe("1m 30s");
    expect(formatDuration(3_600_000)).toBe("60m 00s");
  });
});
