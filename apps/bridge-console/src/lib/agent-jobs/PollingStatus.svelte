<script lang="ts">
  let {
    active,
    paused,
    loading,
    lastUpdated,
    failure,
    label = "polling",
  }: {
    active: boolean;
    paused: boolean;
    loading: boolean;
    lastUpdated?: string;
    failure?: string;
    label?: string;
  } = $props();
</script>

<div class="inline-flex flex-wrap items-center gap-2 rounded-full border border-white/10 bg-white/[0.035] px-3 py-1.5 text-xs font-bold text-slate-300" aria-live="polite">
  <span class={`grid h-4 w-4 place-items-center rounded-full border border-current/30 text-[10px] ${loading && !paused ? "poll-spin text-cyan-200" : "text-slate-500"}`} aria-hidden="true">R</span>
  <span>{paused ? "Paused while hidden" : active ? label : "Manual refresh"}</span>
  {#if lastUpdated}
    <span class="text-slate-500">updated {lastUpdated}</span>
  {/if}
  {#if failure}
    <span class="text-amber-100">stale after failed refresh</span>
  {/if}
</div>

<style>
  :global(.poll-spin) {
    animation: poll-spin 900ms linear infinite;
  }

  @keyframes poll-spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    :global(.poll-spin) {
      animation: none;
    }
  }
</style>
