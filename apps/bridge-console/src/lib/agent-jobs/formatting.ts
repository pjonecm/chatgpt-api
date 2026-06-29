import type { AgentJob, AgentJobStatus } from "./types";

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled", "expired"]);
const SECRET_KEY_RE =
  /(authorization|cookie|access[_-]?token|refresh[_-]?token|bearer|api[_-]?key|secret|password|passphrase|sentinel|proof[_-]?token|conduit|master[_-]?key)/i;
const WINDOWS_PATH_RE = /\b[A-Za-z]:\\[^\s"'<>]+/g;
const POSIX_SECRET_PATH_RE = /\/(?:Users|home|data|var|tmp|secrets|outputs)\/[^\s"'<>]+/g;
const BEARER_RE = /\bBearer\s+[A-Za-z0-9._\-+=/]+/gi;

export function isTerminalStatus(status: AgentJobStatus | undefined | null) {
  return TERMINAL_STATUSES.has(String(status ?? ""));
}

export function statusMeta(status: AgentJobStatus | undefined | null) {
  const value = String(status ?? "unknown");
  const map: Record<string, { label: string; tone: "ok" | "bad" | "warn" | "neutral"; icon: string }> = {
    accepted: { label: "Accepted", tone: "neutral", icon: "Clock" },
    validating: { label: "Validating", tone: "neutral", icon: "Search" },
    queued: { label: "Queued", tone: "warn", icon: "Hourglass" },
    running: { label: "Running", tone: "warn", icon: "Play" },
    streaming: { label: "Streaming", tone: "warn", icon: "Activity" },
    retry_wait: { label: "Retry wait", tone: "warn", icon: "RefreshCw" },
    cancel_requested: { label: "Cancel requested", tone: "warn", icon: "CircleX" },
    succeeded: { label: "Succeeded", tone: "ok", icon: "CheckCircle2" },
    failed: { label: "Failed", tone: "bad", icon: "AlertOctagon" },
    cancelled: { label: "Cancelled", tone: "neutral", icon: "Ban" },
    expired: { label: "Expired", tone: "neutral", icon: "Clock" },
  };
  return map[value] ?? { label: labelize(value), tone: "neutral" as const, icon: "CircleHelp" };
}

export function typeLabel(type: string | undefined | null) {
  if (type === "deep_research") return "Deep Research";
  if (type === "chat") return "Chat";
  return labelize(String(type || "unknown"));
}

export function labelize(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function formatDuration(start?: string | null, end?: string | null) {
  if (!start) return "-";
  const startMs = Date.parse(start);
  const endMs = end ? Date.parse(end) : Date.now();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) return "-";
  const seconds = Math.round((endMs - startMs) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes < 60) return `${minutes}m ${rest}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function jobDuration(job: AgentJob) {
  const start = job.started_at || job.queued_at || job.created_at;
  const end = job.completed_at || job.cancelled_at || (isTerminalStatus(job.status) ? job.completed_at : null);
  return formatDuration(start, end);
}

export function formatBytes(value?: number | null) {
  if (!Number.isFinite(value ?? NaN)) return "-";
  const bytes = Number(value);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function compactId(value?: string | null, size = 9) {
  if (!value) return "-";
  if (value.length <= size * 2 + 1) return value;
  return `${value.slice(0, size)}...${value.slice(-size)}`;
}

export function redactValue(value: unknown, key = ""): unknown {
  if (SECRET_KEY_RE.test(key)) return "<redacted>";
  if (typeof value === "string") {
    return value
      .replace(BEARER_RE, "Bearer <redacted>")
      .replace(WINDOWS_PATH_RE, "<local-path-redacted>")
      .replace(POSIX_SECRET_PATH_RE, "<local-path-redacted>");
  }
  if (Array.isArray(value)) return value.map((item) => redactValue(item));
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [childKey, childValue] of Object.entries(value as Record<string, unknown>)) {
      if (/^(path|local_path|request_storage_key|response_storage_key)$/i.test(childKey)) {
        out[childKey] = "<local-path-redacted>";
      } else {
        out[childKey] = redactValue(childValue, childKey);
      }
    }
    return out;
  }
  return value;
}

export function safeJson(value: unknown) {
  return JSON.stringify(redactValue(value), null, 2);
}

export function normalizeDownloadUrl(url: string, baseUrl: string) {
  if (!url) return "";
  return new URL(url, baseUrl.replace(/\/v1\/?$/, "")).href;
}
