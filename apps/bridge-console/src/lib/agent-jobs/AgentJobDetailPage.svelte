<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import {
    AgentJobApiError,
    buildAgentFetch,
    fetchArtifactText,
    getAgentJob,
    getAgentJobArtifacts,
    getAgentJobEvents,
    getAgentJobResult,
    toFailure,
  } from "./api";
  import {
    formatDate,
    formatDuration,
    isTerminalStatus,
    jobDuration,
    safeJson,
    typeLabel,
  } from "./formatting";
  import JobArtifactList from "./JobArtifactList.svelte";
  import JobErrorPanel from "./JobErrorPanel.svelte";
  import JobResultViewer from "./JobResultViewer.svelte";
  import JobStatusBadge from "./JobStatusBadge.svelte";
  import JobTimeline from "./JobTimeline.svelte";
  import JobTypeBadge from "./JobTypeBadge.svelte";
  import PollingStatus from "./PollingStatus.svelte";
  import type { AgentJob, ApiFailure, JobArtifact, JobEvent, JobResult } from "./types";

  let {
    jobId,
    baseUrl,
    apiKey,
    onBack,
  }: {
    jobId: string;
    baseUrl: string;
    apiKey: string;
    onBack: () => void;
  } = $props();

  let job = $state<AgentJob | null>(null);
  let events = $state<JobEvent[]>([]);
  let artifacts = $state<JobArtifact[]>([]);
  let result = $state<JobResult | null>(null);
  let statusFailure = $state<ApiFailure | null>(null);
  let resultFailure = $state<ApiFailure | null>(null);
  let artifactsFailure = $state<ApiFailure | null>(null);
  let eventsFailure = $state<ApiFailure | null>(null);
  let markdownPreview = $state("");
  let markdownFailure = $state("");
  let loading = $state(true);
  let refreshInFlight = false;
  let lastUpdated = $state("");
  let hidden = $state(false);
  let intervalId: number | null = null;

  const validJobId = $derived(/^job_[A-Za-z0-9]+$/.test(jobId));
  const terminal = $derived(job ? isTerminalStatus(job.status) : false);

  onMount(() => {
    hidden = document.hidden;
    const onVisibility = () => {
      hidden = document.hidden;
      if (!hidden) void refreshDetail(false);
    };
    document.addEventListener("visibilitychange", onVisibility);
    if (validJobId) void refreshDetail(true);
    intervalId = window.setInterval(() => {
      if (!document.hidden && job && !isTerminalStatus(job.status)) void refreshDetail(false);
    }, 3000);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      if (intervalId !== null) window.clearInterval(intervalId);
    };
  });

  onDestroy(() => {
    if (intervalId !== null) window.clearInterval(intervalId);
  });

  async function refreshDetail(initial = false) {
    if (!validJobId) return;
    if (refreshInFlight) return;
    refreshInFlight = true;
    loading = initial || job === null;
    const apiFetch = buildAgentFetch(baseUrl, apiKey);
    try {
      const loaded = await getAgentJob(apiFetch, jobId);
      job = loaded;
      statusFailure = null;
      lastUpdated = new Date().toLocaleTimeString();
      await Promise.all([loadEvents(apiFetch), loadArtifacts(apiFetch), loadResult(apiFetch, loaded)]);
    } catch (error) {
      statusFailure = toFailure(error);
    } finally {
      loading = false;
      refreshInFlight = false;
    }
  }

  async function loadEvents(apiFetch = buildAgentFetch(baseUrl, apiKey)) {
    try {
      events = (await getAgentJobEvents(apiFetch, jobId)).events;
      eventsFailure = null;
    } catch (error) {
      eventsFailure = toFailure(error);
    }
  }

  async function loadArtifacts(apiFetch = buildAgentFetch(baseUrl, apiKey)) {
    try {
      artifacts = (await getAgentJobArtifacts(apiFetch, jobId)).artifacts;
      artifactsFailure = null;
    } catch (error) {
      artifactsFailure = toFailure(error);
    }
  }

  async function loadResult(apiFetch = buildAgentFetch(baseUrl, apiKey), loadedJob = job) {
    try {
      result = await getAgentJobResult(apiFetch, jobId);
      resultFailure = null;
      void maybeLoadMarkdownPreview(result);
    } catch (error) {
      const failure = toFailure(error);
      if (failure.status === 409 && (failure.code === "pending" || failure.code === "job_failed")) {
        result = null;
        resultFailure = failure;
        return;
      }
      if (error instanceof AgentJobApiError && loadedJob && !isTerminalStatus(loadedJob.status)) {
        resultFailure = failure;
        return;
      }
      resultFailure = failure;
    }
  }

  async function maybeLoadMarkdownPreview(loaded: JobResult | null) {
    markdownPreview = "";
    markdownFailure = "";
    if (!loaded || loaded.result_type !== "research") return;
    const artifact =
      loaded.artifacts?.find((item) => item.content_type?.includes("markdown") || /\.md$/i.test(item.filename)) ??
      artifacts.find((item) => item.content_type?.includes("markdown") || /\.md$/i.test(item.filename));
    if (!artifact?.download_url) return;
    try {
      markdownPreview = await fetchArtifactText(baseUrl, apiKey, artifact.download_url);
    } catch (error) {
      markdownFailure = error instanceof Error ? error.message : String(error);
    }
  }
</script>

<section class="grid gap-4">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <button class="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-black text-slate-200" onclick={onBack}>
      <span aria-hidden="true">&lt;</span>
      Back to Agent Jobs
    </button>
    <div class="flex flex-wrap gap-2">
      <PollingStatus active={Boolean(job && !terminal)} paused={hidden} {loading} {lastUpdated} failure={statusFailure?.message} label="polling every 3s" />
      <button class="inline-flex items-center gap-2 rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-sm font-black text-cyan-100" onclick={() => refreshDetail(false)} disabled={loading || !validJobId}>
        <span aria-hidden="true">R</span>
        Refresh
      </button>
    </div>
  </div>

  {#if !validJobId}
    <div class="rounded-2xl border border-rose-300/30 bg-rose-300/10 p-5 text-rose-100">Invalid Agent Job route. Job IDs must use the public `job_...` identifier.</div>
  {:else if loading && !job}
    <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-slate-400">Loading Agent Job...</div>
  {:else if statusFailure && !job}
    <div class="rounded-2xl border border-rose-300/30 bg-rose-300/10 p-5 text-rose-100">
      <strong>{statusFailure.status === 404 ? "Job not found" : statusFailure.status === 401 ? "Unauthorized" : "Unable to load job"}:</strong>
      {statusFailure.message}
    </div>
  {:else if job}
    <article class="rounded-2xl border border-white/10 bg-[#0b0d12] p-5">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0">
          <p class="text-xs font-black uppercase tracking-[0.16em] text-cyan-200">Agent Job</p>
          <h3 class="mt-1 break-all font-mono text-xl font-black text-white">{job.job_id}</h3>
          <div class="mt-3 flex flex-wrap gap-2">
            <JobStatusBadge status={job.status} />
            <JobTypeBadge type={job.type} />
          </div>
        </div>
        <div class="grid gap-2 text-right text-sm text-slate-400">
          <span>{typeLabel(job.type)} · {job.model || "-"}</span>
          <span>Elapsed {jobDuration(job)}</span>
        </div>
      </div>

      <div class="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {#each [
          ["Client request ID", job.client_request_id || "-"],
          ["Account alias", job.account_alias || "-"],
          ["Attempts", `${job.attempt_count ?? 0}/${job.max_attempts ?? "-"}`],
          ["Result", job.result_available ? "available" : "not available"],
          ["Artifacts", String(job.artifact_count ?? artifacts.length)],
          ["Created", formatDate(job.created_at)],
          ["Queued", formatDate(job.queued_at)],
          ["Started", formatDate(job.started_at)],
          ["Cancel requested", formatDate(job.cancel_requested_at)],
          ["Completed", formatDate(job.completed_at)],
          ["Cancelled", formatDate(job.cancelled_at)],
          ["Duration", formatDuration(job.started_at || job.queued_at || job.created_at, job.completed_at || job.cancelled_at)],
        ] as item (item[0])}
          <div class="rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <div class="text-[11px] font-black uppercase tracking-[0.12em] text-slate-500">{item[0]}</div>
            <div class="mt-1 break-all text-sm font-black text-slate-100">{item[1]}</div>
          </div>
        {/each}
      </div>
    </article>

    <JobErrorPanel error={job.error} uiFailure={statusFailure} />

    <div class="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <JobTimeline {events} />
      <div class="grid gap-4">
        <div class="rounded-2xl border border-white/10 bg-black/20 p-4">
          <h3 class="text-sm font-black uppercase tracking-[0.12em] text-slate-300">Attempts</h3>
          <p class="mt-3 text-sm text-slate-500">Attempt rows are not included in the shipped detail, events, result, or artifact endpoint contracts. Showing summary count only: {job.attempt_count ?? 0}/{job.max_attempts ?? "-"}.</p>
        </div>
        {#if eventsFailure}
          <div class="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-4 text-sm text-amber-100">Timeline refresh failed: {eventsFailure.message}</div>
        {/if}
      </div>
    </div>

    <JobResultViewer {job} {result} {resultFailure} {markdownPreview} {markdownFailure} {baseUrl} />
    <JobArtifactList {artifacts} {baseUrl} failure={artifactsFailure?.message} />

    <details class="rounded-2xl border border-white/10 bg-black/20 p-4">
      <summary class="cursor-pointer text-sm font-black uppercase tracking-[0.12em] text-slate-300">Status JSON (redacted)</summary>
      <pre class="mt-4 max-h-[520px] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-slate-950/70 p-4 font-mono text-xs text-slate-300">{safeJson(job)}</pre>
    </details>
  {/if}
</section>
