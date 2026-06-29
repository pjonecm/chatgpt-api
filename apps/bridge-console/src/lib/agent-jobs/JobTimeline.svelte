<script lang="ts">
  import { safeJson } from "./formatting";
  import type { JobEvent } from "./types";

  let { events }: { events: JobEvent[] } = $props();
</script>

<div class="rounded-2xl border border-white/10 bg-black/20 p-4">
  <h3 class="text-sm font-black uppercase tracking-[0.12em] text-slate-300">Timeline</h3>
  {#if events.length === 0}
    <p class="mt-3 text-sm text-slate-500">No state-transition events were returned for this job.</p>
  {:else}
    <ol class="mt-4 grid gap-3">
      {#each events as event, index (`${event.event_id ?? "event"}-${event.sequence_no ?? index}`)}
        <li class="grid gap-3 rounded-xl border border-white/10 bg-white/[0.025] p-3 md:grid-cols-[74px_minmax(150px,0.45fr)_minmax(0,1fr)]">
          <div class="font-mono text-xs text-slate-500">#{event.sequence_no ?? index + 1}</div>
          <div>
            <div class="break-all text-sm font-black text-slate-100">{event.event_type || "event"}</div>
            <div class="mt-1 text-xs text-slate-500">{event.created_at || "-"}</div>
          </div>
          <pre class="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-950/70 p-3 font-mono text-xs text-slate-300">{safeJson(event.data ?? {})}</pre>
        </li>
      {/each}
    </ol>
  {/if}
</div>
