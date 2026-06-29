<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { buildAgentFetch, listAgentJobs, toFailure } from "./api";
  import { isTerminalStatus, jobDuration } from "./formatting";
  import JobFilters from "./JobFilters.svelte";
  import JobTable from "./JobTable.svelte";
  import PollingStatus from "./PollingStatus.svelte";
  import type { AgentJob, AgentJobFilters, ApiFailure } from "./types";

  let {
    baseUrl,
    apiKey,
    onOpenJob,
  }: {
    baseUrl: string;
    apiKey: string;
    onOpenJob: (jobId: string) => void;
  } = $props();

  let jobs = $state<AgentJob[]>([]);
  let filters = $state<AgentJobFilters>({
    status: "",
    type: "",
    model: "",
    account: "",
    client_request_id: "",
    error_code: "",
    search: "",
  });
  let cursorStack = $state<(string | null)[]>([null]);
  let pageIndex = $state(0);
  let nextCursor = $state<string | null>(null);
  let hasMore = $state(false);
  let loading = $state(true);
  let refreshInFlight = false;
  let refreshFailure = $state<ApiFailure | null>(null);
  let lastUpdated = $state("");
  let hidden = $state(false);
  let intervalId: number | null = null;

  const visibleJobs = $derived(
    filters.search.trim()
      ? jobs.filter((job) => job.job_id.toLowerCase().includes(filters.search.trim().toLowerCase()))
      : jobs,
  );
  const counts = $derived(buildVisibleCounts(visibleJobs));
  const activePolling = $derived(visibleJobs.some((job) => !isTerminalStatus(job.status)));

  onMount(() => {
    hidden = document.hidden;
    const onVisibility = () => {
      hidden = document.hidden;
      if (!hidden) void refreshCurrent(false);
    };
    document.addEventListener("visibilitychange", onVisibility);
    void refreshCurrent(true);
    intervalId = window.setInterval(() => {
      if (!document.hidden) void refreshCurrent(false);
    }, 5000);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      if (intervalId !== null) window.clearInterval(intervalId);
    };
  });

  onDestroy(() => {
    if (intervalId !== null) window.clearInterval(intervalId);
  });

  async function refreshCurrent(initial = false) {
    if (refreshInFlight) return;
    refreshInFlight = true;
    loading = initial || jobs.length === 0;
    try {
      const apiFetch = buildAgentFetch(baseUrl, apiKey);
      const page = await listAgentJobs(apiFetch, filters, cursorStack[pageIndex] ?? null, 50);
      jobs = page.jobs;
      nextCursor = page.next_cursor ?? null;
      hasMore = Boolean(page.has_more);
      refreshFailure = null;
      lastUpdated = new Date().toLocaleTimeString();
    } catch (error) {
      refreshFailure = toFailure(error);
    } finally {
      loading = false;
      refreshInFlight = false;
    }
  }

  function applyFilters() {
    pageIndex = 0;
    cursorStack = [null];
    void refreshCurrent(true);
  }

  function clearFilters() {
    filters = {
      status: "",
      type: "",
      model: "",
      account: "",
      client_request_id: "",
      error_code: "",
      search: "",
    };
    pageIndex = 0;
    cursorStack = [null];
    void refreshCurrent(true);
  }

  function nextPage() {
    if (!hasMore || !nextCursor) return;
    cursorStack = [...cursorStack.slice(0, pageIndex + 1), nextCursor];
    pageIndex += 1;
    void refreshCurrent(true);
  }

  function previousPage() {
    if (pageIndex <= 0) return;
    pageIndex -= 1;
    void refreshCurrent(true);
  }

  function buildVisibleCounts(rows: AgentJob[]) {
    const out: Record<string, number> = {};
    for (const job of rows) out[job.status] = (out[job.status] ?? 0) + 1;
    return out;
  }
</script>

<section class="grid gap-4">
  <article class="rounded-2xl border border-white/10 bg-[#0b0d12] p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="text-xs font-black uppercase tracking-[0.16em] text-cyan-200">visible on this page</p>
        <h3 class="mt-1 text-xl font-black text-white">Agent Job Monitor</h3>
        <p class="mt-2 max-w-3xl text-sm leading-relaxed text-slate-400">
          Read-only view over shipped Agent Job endpoints. Counts and job-ID search apply only to the currently loaded page.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <PollingStatus active={activePolling} paused={hidden} {loading} {lastUpdated} failure={refreshFailure?.message} label="polling every 5s" />
        <button class="inline-flex items-center gap-2 rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-sm font-black text-cyan-100" onclick={() => refreshCurrent(false)} disabled={loading}>
          <span aria-hidden="true">R</span>
          Refresh
        </button>
      </div>
    </div>

    <div class="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-6">
      {#each ["queued", "running", "retry_wait", "succeeded", "failed", "cancelled"] as key}
        <div class="rounded-xl border border-white/10 bg-white/[0.03] p-3">
          <div class="text-[11px] font-black uppercase tracking-[0.12em] text-slate-500">{key.replace("_", " ")}</div>
          <div class="mt-1 text-2xl font-black text-slate-100">{counts[key] ?? 0}</div>
        </div>
      {/each}
    </div>
  </article>

  <JobFilters bind:filters disabled={loading} onApply={applyFilters} onClear={clearFilters} />

  {#if refreshFailure}
    <div class={`rounded-2xl border p-4 text-sm ${refreshFailure.status === 401 ? "border-rose-300/30 bg-rose-300/10 text-rose-100" : "border-amber-300/30 bg-amber-300/10 text-amber-100"}`}>
      <strong>{refreshFailure.status === 401 ? "Unauthorized" : refreshFailure.code === "malformed_data" ? "Malformed Agent Job response" : "Agent Job refresh failed"}:</strong>
      {refreshFailure.message}
      {#if jobs.length}
        <span class="ml-2 text-slate-300">Showing last-known page data.</span>
      {/if}
    </div>
  {/if}

  {#if loading && jobs.length === 0}
    <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-slate-400" aria-live="polite">Loading Agent Jobs...</div>
  {:else if jobs.length === 0 && !refreshFailure}
    <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-slate-400">No Agent Jobs exist yet.</div>
  {:else if visibleJobs.length === 0}
    <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-slate-400">No jobs match the page-local job ID search.</div>
  {:else}
    <JobTable jobs={visibleJobs} onOpen={onOpenJob} />
  {/if}

  <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-black/20 p-3 text-sm text-slate-400">
    <div>
      Page {pageIndex + 1}. Showing {visibleJobs.length} visible row(s) from the current API page.
      {#if hasMore}
        <span>More pages are available.</span>
      {:else}
        <span>No next cursor returned.</span>
      {/if}
    </div>
    <div class="flex gap-2">
      <button class="rounded-xl border border-white/10 bg-white/5 px-3 py-2 font-black text-slate-200" onclick={previousPage} disabled={pageIndex === 0 || loading}>Previous</button>
      <button class="rounded-xl border border-white/10 bg-white/5 px-3 py-2 font-black text-slate-200" onclick={nextPage} disabled={!hasMore || !nextCursor || loading}>Next</button>
    </div>
  </div>
</section>
