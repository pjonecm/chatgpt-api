export type AgentJobStatus =
  | "accepted"
  | "validating"
  | "queued"
  | "running"
  | "streaming"
  | "retry_wait"
  | "cancel_requested"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "expired"
  | string;

export type JobError = {
  code?: string | null;
  message?: string | null;
};

export type AgentJob = {
  job_id: string;
  type: string;
  status: AgentJobStatus;
  model?: string | null;
  account_alias?: string | null;
  attempt_count?: number | null;
  max_attempts?: number | null;
  client_request_id?: string | null;
  created_at?: string | null;
  queued_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  cancel_requested_at?: string | null;
  cancelled_at?: string | null;
  expires_at?: string | null;
  result_available?: boolean | null;
  artifact_count?: number | null;
  error?: JobError | null;
};

export type AgentJobListResponse = {
  jobs: AgentJob[];
  next_cursor?: string | null;
  has_more?: boolean;
};

export type JobEvent = {
  event_id?: string;
  sequence_no?: number;
  event_type?: string;
  data?: Record<string, unknown>;
  created_at?: string | null;
};

export type JobEventsResponse = {
  job_id: string;
  events: JobEvent[];
  next_cursor?: string | null;
  has_more?: boolean;
};

export type JobArtifact = {
  file_id: string;
  filename: string;
  download_url: string;
  content_type?: string | null;
  bytes?: number | null;
  created_at?: string | null;
};

export type JobArtifactsResponse = {
  job_id: string;
  artifacts: JobArtifact[];
};

export type JobResult = {
  job_id: string;
  result_type: string;
  created_at?: string | null;
  text?: string;
  model?: string | null;
  account_alias?: string | null;
  finish_reason?: string | null;
  response?: unknown;
  artifacts?: JobArtifact[];
};

export type AgentJobFilters = {
  status: string;
  type: string;
  model: string;
  account: string;
  client_request_id: string;
  error_code: string;
  search: string;
};

export type ApiFetch = <T = unknown>(
  path: string,
  options?: RequestInit,
) => Promise<T>;

export type ApiFailure = {
  status: number | null;
  code: string;
  message: string;
};
