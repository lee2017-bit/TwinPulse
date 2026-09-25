import { beforeEach, describe, expect, it, vi } from "vitest";
import { TwinPulseApi } from "./api";

const jsonResponse = (status: number, body: object): Response => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
}) as Response;

describe("TwinPulse browser session recovery", () => {
  beforeEach(() => {
    history.replaceState(null, "", "/");
  });

  it("consumes the fragment bootstrap once and removes it before awaiting the network", async () => {
    history.replaceState(null, "", "/#bootstrap=one-time-secret");
    const fetchMock = vi.fn(async () => {
      expect(window.location.hash).toBe("");
      return jsonResponse(200, { csrf_token: "csrf-1" });
    });
    vi.stubGlobal("fetch", fetchMock);

    await new TwinPulseApi().bootstrap();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/v1/bootstrap", expect.objectContaining({ method: "POST" }));
    expect(sessionStorage.getItem("twinpulse.csrf")).toBe("csrf-1");
  });

  it("rehydrates a new tab from the HttpOnly cookie without another bootstrap secret", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, {
      role: "product", csrf_token: "csrf-reopened",
      idle_expires_in_s: 1800, absolute_expires_in_s: 28000,
    }));
    vi.stubGlobal("fetch", fetchMock);

    await new TwinPulseApi().bootstrap();

    expect(fetchMock).toHaveBeenCalledWith("/v1/product/session", expect.objectContaining({
      method: "GET", credentials: "same-origin",
    }));
    expect(sessionStorage.getItem("twinpulse.csrf")).toBe("csrf-reopened");
  });

  it("clears stale tab state and reports a finite reopen error", async () => {
    sessionStorage.setItem("twinpulse.csrf", "stale");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, {
      error: { code: "session_rejected", message: "expired" },
    })));

    await expect(new TwinPulseApi().bootstrap()).rejects.toMatchObject({
      code: "session_reopen_required",
    });
    expect(sessionStorage.getItem("twinpulse.csrf")).toBeNull();
  });

  it("never retries a rejected state-changing request", async () => {
    sessionStorage.setItem("twinpulse.csrf", "csrf");
    const fetchMock = vi.fn(async () => jsonResponse(401, {
      error: { code: "session_rejected", message: "expired" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(new TwinPulseApi().generate()).rejects.toMatchObject({
      code: "session_reopen_required",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem("twinpulse.csrf")).toBeNull();
  });
});
