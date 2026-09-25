import type { CommandType } from "./engine-contracts";
import type { ProductState, ProviderSettingsState, SupervisorState, WorkflowState } from "./types";

const CSRF_KEY = "twinpulse.csrf";

export class ApiError extends Error {
  constructor(public readonly code: string, message: string) {
    super(message);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  const body = await response.json() as { error?: { code?: string; message?: string } } & T;
  if (!response.ok) {
    throw new ApiError(body.error?.code ?? "request_failed", body.error?.message ?? "요청이 실패했습니다.");
  }
  return body;
}

export class TwinPulseApi {
  private csrf = sessionStorage.getItem(CSRF_KEY) ?? "";

  private saveCsrf(value: string): void {
    this.csrf = value;
    sessionStorage.setItem(CSRF_KEY, value);
  }

  private clearCsrf(): void {
    this.csrf = "";
    sessionStorage.removeItem(CSRF_KEY);
  }

  private reopenRequired(): ApiError {
    return new ApiError(
      "session_reopen_required",
      "세션이 만료되었습니다. TwinPulse 런처의 안전한 시작 링크로 다시 열어주세요.",
    );
  }

  async bootstrap(): Promise<void> {
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const secret = fragment.get("bootstrap");
    if (!secret) {
      try {
        const recovered = await parseResponse<{ csrf_token: string }>(await fetch(
          "/v1/product/session",
          { method: "GET", credentials: "same-origin" },
        ));
        this.saveCsrf(recovered.csrf_token);
        return;
      } catch (error) {
        this.clearCsrf();
        if (error instanceof ApiError && error.code === "session_rejected") {
          throw this.reopenRequired();
        }
        throw error;
      }
    }
    history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    try {
      const result = await parseResponse<{ csrf_token: string }>(await fetch("/v1/bootstrap", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: "product", secret }),
      }));
      this.saveCsrf(result.csrf_token);
    } catch (error) {
      this.clearCsrf();
      throw error;
    }
  }

  private async request<T>(path: string, body?: object): Promise<T> {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      headers: body === undefined ? undefined : {
        "Content-Type": "application/json",
        "X-TwinPulse-CSRF": this.csrf,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    try {
      return await parseResponse<T>(response);
    } catch (error) {
      if (response.status === 401) {
        this.clearCsrf();
        throw this.reopenRequired();
      }
      throw error;
    }
  }

  workflow(): Promise<WorkflowState> { return this.request("/v1/product/workflow"); }
  productState(): Promise<ProductState> { return this.request("/v1/product/state"); }
  runtimeState(): Promise<SupervisorState> { return this.request("/v1/product/runtime"); }
  providerSettings(): Promise<ProviderSettingsState> {
    return this.request("/v1/product/provider-settings");
  }
  saveProviderSettings(body: {
    base_url: string; model_id: string; reasoning_effort: string; api_key: string;
    credential_reapproval: boolean; provider_profile: string;
  }): Promise<ProviderSettingsState> {
    return this.request("/v1/product/provider-settings", body);
  }
  selectInput(body: object): Promise<WorkflowState> { return this.request("/v1/product/input", body); }
  generate(): Promise<WorkflowState> { return this.request("/v1/product/generation", {}); }
  cancelGeneration(): Promise<WorkflowState> { return this.request("/v1/product/generation/cancel", {}); }
  acknowledge(revision: string): Promise<WorkflowState> {
    return this.request("/v1/product/draft/acknowledge", { revision });
  }
  acquireLease(): Promise<{ control_lease_id: string; ttl_s: number }> {
    return this.request("/v1/product/lease", {});
  }
  renewLease(controlLeaseId: string): Promise<{ control_lease_id: string; ttl_s: number }> {
    return this.request("/v1/product/lease/renew", { control_lease_id: controlLeaseId });
  }
  command(
    commandType: CommandType,
    expectedAppliedRevision: string | null,
    artifactId?: string,
  ): Promise<{ command_id: string; status: string }> {
    return this.request("/v1/product/commands", {
      client_request_id: crypto.randomUUID(),
      command_type: commandType,
      expected_applied_revision: expectedAppliedRevision,
      ...(artifactId ? { artifact_id: artifactId } : {}),
    });
  }
}

export async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 32_768) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32_768));
  }
  return btoa(binary);
}
