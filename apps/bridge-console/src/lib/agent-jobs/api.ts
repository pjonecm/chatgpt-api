import type {
  AgentJob,
  AgentJobFilters,
  AgentJobListResponse,
  ApiFailure,
  ApiFetch,
  JobArtifactsResponse,
  JobEventsResponse,
  JobResult,
} from "./types";

export class AgentJobApiError extends Error {
  status: number | null;
  code: string;

  constructor(message: string, status: number | null, code = "request_failed") {
    super(message);
    this.name = "AgentJobApiError";
    this.status = status;
    this.code = code;
  }
}

export function toFailure(error: unknown): ApiFailure {
  if (error instanceof AgentJobApiError) {
    return { status: error.status, code: error.code, message: error.message };
  }
  return {
    status: null,
    code: "network_error",
    message: error instanceof Error ? error.message : String(error),
  };
}

export async function rawApiFetch<T = unknown>(
  baseUrl: string,
  apiKey: string,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${baseUrl.replace(/\/+$/, "")}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const error = payload?.error ?? {};
    throw new AgentJobApiError(
      String(error.message || payload || `HTTP ${response.status}`),
      response.status,
      String(error.code || response.status),
    );
  }
  return payload as T;
}

export function buildAgentFetch(baseUrl: string, apiKey: string): ApiFetch {
  return (path, options) => rawApiFetch(baseUrl, apiKey, path, options);
}

export async function listAgentJobs(
  apiFetch: ApiFetch,
  filters: AgentJobFilters,
  cursor: string | null,
  limit = 50,
) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.type) params.set("type", filters.type);
  if (filters.model) params.set("model", filters.model);
  if (filters.account) params.set("account", filters.account);
  if (filters.client_request_id) params.set("client_request_id", filters.client_request_id);
  if (filters.error_code) params.set("error_code", filters.error_code);
  params.set("limit", String(limit));
  if (cursor) params.set("cursor", cursor);
  const query = params.toString();
  const payload = await apiFetch<AgentJobListResponse>(`/agent/jobs${query ? `?${query}` : ""}`);
  if (!payload || !Array.isArray(payload.jobs)) {
    throw new AgentJobApiError("Agent Jobs list response was malformed.", null, "malformed_data");
  }
  return payload;
}

export async function getAgentJob(apiFetch: ApiFetch, jobId: string) {
  const payload = await apiFetch<AgentJob>(`/agent/jobs/${encodeURIComponent(jobId)}`);
  if (!payload?.job_id || !payload.status) {
    throw new AgentJobApiError("Agent Job status response was malformed.", null, "malformed_data");
  }
  return payload;
}

export async function getAgentJobEvents(apiFetch: ApiFetch, jobId: string) {
  const payload = await apiFetch<JobEventsResponse>(`/agent/jobs/${encodeURIComponent(jobId)}/events`);
  if (!payload || !Array.isArray(payload.events)) {
    throw new AgentJobApiError("Agent Job events response was malformed.", null, "malformed_data");
  }
  return payload;
}

export async function getAgentJobArtifacts(apiFetch: ApiFetch, jobId: string) {
  const payload = await apiFetch<JobArtifactsResponse>(`/agent/jobs/${encodeURIComponent(jobId)}/artifacts`);
  if (!payload || !Array.isArray(payload.artifacts)) {
    throw new AgentJobApiError("Agent Job artifacts response was malformed.", null, "malformed_data");
  }
  return payload;
}

export async function getAgentJobResult(apiFetch: ApiFetch, jobId: string) {
  return apiFetch<JobResult>(`/agent/jobs/${encodeURIComponent(jobId)}/result`);
}

export async function fetchArtifactText(baseUrl: string, apiKey: string, downloadUrl: string) {
  const absolute = new URL(downloadUrl, baseUrl.replace(/\/v1\/?$/, "")).href;
  const response = await fetch(absolute, {
    headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
  });
  if (!response.ok) {
    throw new AgentJobApiError(`Artifact preview failed with HTTP ${response.status}.`, response.status, "artifact_unavailable");
  }
  return response.text();
}
