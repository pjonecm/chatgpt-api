<script lang="ts">
  import { compactId, formatDate, jobDuration } from "./formatting";
  import JobStatusBadge from "./JobStatusBadge.svelte";
  import JobTypeBadge from "./JobTypeBadge.svelte";
  import type { AgentJob } from "./types";

  let {
    jobs,
    onOpen,
  }: {
    jobs: AgentJob[];
    onOpen: (jobId: string) => void;
  } = $props();
</script>

<div class="overflow-x-auto rounded-2xl border border-white/10">
  <table class="w-full min-w-[1180px] border-collapse text-left">
    <thead class="bg-white/[0.035]">
      <tr>
        {#each ["Job", "Client", "Type", "Status", "Model", "Account", "Attempts", "Timing", "Result", "Artifacts", "Error", "Open"] as header}
          <th class="border-b border-white/10 px-3 py-3 text-[11px] font-black uppercase tracking-[0.12em] text-slate-500">{header}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each jobs as job (job.job_id)}
        <tr class="border-b border-white/7 align-top hover:bg-cyan-300/[0.035]">
          <td class="px-3 py-3">
            <button class="max-w-[190px] break-all text-left font-mono text-xs font-black text-cyan-100 hover:underline" onclick={() => onOpen(job.job_id)} title={job.job_id}>
              {compactId(job.job_id, 10)}
            </button>
          </td>
          <td class="px-3 py-3">
            <div class="max-w-[170px] break-all font-mono text-xs text-slate-300">{job.client_request_id || "-"}</div>
          </td>
          <td class="px-3 py-3"><JobTypeBadge type={job.type} /></td>
          <td class="px-3 py-3"><JobStatusBadge status={job.status} /></td>
          <td class="px-3 py-3"><div class="max-w-[150px] break-all text-sm text-slate-300">{job.model || "-"}</div></td>
          <td class="px-3 py-3"><div class="max-w-[130px] break-all text-sm text-slate-300">{job.account_alias || "-"}</div></td>
          <td class="px-3 py-3 text-sm text-slate-300">{job.attempt_count ?? 0}/{job.max_attempts ?? "-"}</td>
          <td class="px-3 py-3">
            <div class="grid gap-1 text-xs text-slate-400">
              <span>Created {formatDate(job.created_at)}</span>
              <span>Started {formatDate(job.started_at)}</span>
              <strong class="text-slate-200">{jobDuration(job)}</strong>
            </div>
          </td>
          <td class="px-3 py-3 text-sm">
            {#if job.result_available}
              <span class="text-emerald-100">available</span>
            {:else}
              <span class="text-slate-500">not available</span>
            {/if}
          </td>
          <td class="px-3 py-3 text-sm text-slate-300">{job.artifact_count ?? 0}</td>
          <td class="px-3 py-3">
            {#if job.error?.code}
              <div class="max-w-[170px] break-all rounded-lg border border-rose-300/25 bg-rose-300/10 px-2 py-1 font-mono text-xs text-rose-100">{job.error.code}</div>
            {:else}
              <span class="text-sm text-slate-600">-</span>
            {/if}
          </td>
          <td class="px-3 py-3">
            <button class="inline-flex items-center gap-1.5 rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-xs font-black text-cyan-100" aria-label={`Open Agent Job ${job.job_id}`} onclick={() => onOpen(job.job_id)}>
              <span aria-hidden="true">V</span>
              View
            </button>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
