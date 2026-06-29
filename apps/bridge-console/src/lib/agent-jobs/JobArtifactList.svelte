<script lang="ts">
  import { formatBytes, normalizeDownloadUrl } from "./formatting";
  import type { JobArtifact } from "./types";

  let {
    artifacts,
    baseUrl,
    failure,
  }: {
    artifacts: JobArtifact[];
    baseUrl: string;
    failure?: string | null;
  } = $props();
</script>

<div class="rounded-2xl border border-white/10 bg-black/20 p-4">
  <h3 class="text-sm font-black uppercase tracking-[0.12em] text-slate-300">Artifacts</h3>
  {#if failure}
    <p class="mt-3 rounded-xl border border-amber-300/25 bg-amber-300/10 p-3 text-sm text-amber-100">{failure}</p>
  {/if}
  {#if artifacts.length === 0}
    <p class="mt-3 text-sm text-slate-500">No job-associated artifacts were returned.</p>
  {:else}
    <div class="mt-4 grid gap-3">
      {#each artifacts as artifact (artifact.file_id)}
        <article class="rounded-xl border border-white/10 bg-white/[0.025] p-3">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="grid h-5 w-5 place-items-center rounded-full border border-cyan-200/40 text-xs font-black text-cyan-100" aria-hidden="true">F</span>
                <h4 class="break-all text-sm font-black text-slate-100">{artifact.filename}</h4>
              </div>
              <div class="mt-2 grid gap-1 text-xs text-slate-500 sm:grid-cols-3">
                <span>{artifact.content_type || "application/octet-stream"}</span>
                <span>{formatBytes(artifact.bytes)}</span>
                <span>{artifact.created_at || "-"}</span>
              </div>
              <div class="mt-2 break-all font-mono text-xs text-slate-500">{artifact.download_url}</div>
            </div>
            <div class="flex flex-wrap gap-2">
              <a class="inline-flex items-center gap-1.5 rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-xs font-black text-cyan-100" href={normalizeDownloadUrl(artifact.download_url, baseUrl)} target="_blank" rel="noreferrer">
                <span aria-hidden="true">O</span>
                Open
              </a>
              <a class="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-black text-slate-200" href={normalizeDownloadUrl(artifact.download_url, baseUrl)} download={artifact.filename}>
                <span aria-hidden="true">D</span>
                Download
              </a>
            </div>
          </div>
        </article>
      {/each}
    </div>
  {/if}
</div>
