import { afterEach, describe, expect, it } from "vitest";

import { artifactUrl, getApiBase, setApiBase } from "./api";

afterEach(() => {
  setApiBase("http://127.0.0.1:8000");
});

describe("api base URL", () => {
  it("defaults to the local backend", () => {
    expect(getApiBase()).toBe("http://127.0.0.1:8000");
  });

  it("updates and strips trailing slashes", () => {
    setApiBase("http://example.com:9000/");
    expect(getApiBase()).toBe("http://example.com:9000");
  });
});

describe("artifactUrl", () => {
  it("joins the base with a relative artifact path", () => {
    setApiBase("http://127.0.0.1:8000");
    expect(artifactUrl("/artifacts/job-x/production/final_video.mp4")).toBe(
      "http://127.0.0.1:8000/artifacts/job-x/production/final_video.mp4",
    );
  });
});
