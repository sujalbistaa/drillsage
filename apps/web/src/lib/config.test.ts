import { describe, expect, it } from "vitest";

import { serverApiBaseUrl } from "./config";

describe("serverApiBaseUrl", () => {
  it("prefers an explicit URL, then the Render host, then the public default", () => {
    expect(serverApiBaseUrl({ API_INTERNAL_URL: "http://api:8000", API_RENDER_HOST: "x" })).toBe(
      "http://api:8000",
    );
    expect(serverApiBaseUrl({ API_RENDER_HOST: "drillsage-api-ab12" })).toBe(
      "https://drillsage-api-ab12.onrender.com",
    );
    expect(serverApiBaseUrl({})).toBe("http://localhost:8000");
  });
});
