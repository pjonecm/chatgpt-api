<script lang="ts">
  import CodeBlock from "../CodeBlock.svelte";
  import { isTerminalStatus, normalizeDownloadUrl, safeJson } from "./formatting";
  import type { AgentJob, JobResult } from "./types";

  let {
    job,
    result,
    resultFailure,
    markdownPreview,
    markdownFailure,
    baseUrl,
  }: {
    job: AgentJob;
    result: JobResult | null;
    resultFailure?: { status: number | null; code: string; message: string } | null;
    markdownPreview?: string;
    markdownFailure?: string;
    baseUrl: string;
  } = $props();

  const terminal = $derived(isTerminalStatus(job.status));
  const researchArtifact = $derived(
    result?.artifacts?.find((artifact) =>
      artifact.content_type?.includes("markdown") || /\.md$/i.test(artifact.filename),
    ) ?? null,
  );
</script>

<div class="rounded-2xl border border-white/10 bg-black/20 p-4">
  <h3 class="text-sm font-black uppercase tracking-[0.12em] text-slate-300">Result</h3>
  {#if result}
    {#if result.result_type === "text"}
      <div class="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.06] p-4">
        <pre class="max-h-[520px] overflow-auto whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-100">{result.text || "(empty text result)"}</pre>
      </div>
      {#if result.response}
        <CodeBlock title="Raw normalized response (redacted)" code={safeJson(result.response)} />
      {/if}
    {:else if result.result_type === "research"}
      {#if researchArtifact}
        <div class="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.06] p-3">
          <div class="min-w-0">
            <div class="break-all text-sm font-black text-slate-100">{researchArtifact.filename}</div>
            <div class="mt-1 text-xs text-slate-500">{researchArtifact.content_type || "text/markdown"}</div>
          </div>
          <a class="rounded-xl border border-cyan-300/35 bg-cyan-300/10 px-3 py-2 text-sm font-black text-cyan-100" href={normalizeDownloadUrl(researchArtifact.download_url, baseUrl)} target="_blank" rel="noreferrer">
            Open artifact
          </a>
        </div>
        {#if markdownPreview}
          <div class="mt-4 rounded-xl border border-white/10 bg-slate-950/70 p-4">
            <pre class="max-h-[620px] overflow-auto whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-200">{markdownPreview}</pre>
          </div>
        {:else if markdownFailure}
          <p class="mt-4 rounded-xl border border-amber-300/25 bg-amber-300/10 p-3 text-sm text-amber-100">{markdownFailure}</p>
        {:else}
          <p class="mt-4 text-sm text-slate-500">Markdown preview is loading from the existing artifact download URL.</p>
        {/if}
      {:else}
        <p class="mt-4 rounded-xl border border-amber-300/25 bg-amber-300/10 p-3 text-sm text-amber-100">Research result returned without a markdown artifact in the result payload.</p>
      {/if}
      {#if result.response}
        <CodeBlock title="Raw normalized response (redacted)" code={safeJson(result.response)} />
      {/if}
    {:else}
      <p class="mt-4 rounded-xl border border-amber-300/25 bg-amber-300/10 p-3 text-sm text-amber-100">Unsupported result type: {result.result_type}</p>
      <CodeBlock title="Result JSON (redacted)" code={safeJson(result)} />
    {/if}
  {:else if resultFailure}
    {#if resultFailure.status === 409 && resultFailure.code === "pending"}
      <p class="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm text-slate-400">Result is pending for this non-terminal job.</p>
    {:else if resultFailure.status === 409 && resultFailure.code === "job_failed"}
      <p class="mt-4 rounded-xl border border-rose-300/25 bg-rose-300/10 p-3 text-sm text-rose-100">The job failed without a stored result.</p>
    {:else}
      <p class="mt-4 rounded-xl border border-rose-300/25 bg-rose-300/10 p-3 text-sm text-rose-100">{resultFailure.message}</p>
    {/if}
  {:else if !terminal}
    <p class="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm text-slate-400">Result will appear after the job reaches a terminal success state.</p>
  {:else if job.status === "cancelled"}
    <p class="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm text-slate-400">Cancelled jobs do not expose a result.</p>
  {:else if job.status === "failed"}
    <p class="mt-4 rounded-xl border border-rose-300/25 bg-rose-300/10 p-3 text-sm text-rose-100">No result is available for this failed job.</p>
  {:else}
    <p class="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm text-slate-400">No result was returned for this job.</p>
  {/if}
</div>
