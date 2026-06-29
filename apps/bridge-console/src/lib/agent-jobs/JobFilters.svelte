<script lang="ts">
  import type { AgentJobFilters } from "./types";

  let {
    filters = $bindable(),
    disabled = false,
    onApply,
    onClear,
  }: {
    filters: AgentJobFilters;
    disabled?: boolean;
    onApply: () => void;
    onClear: () => void;
  } = $props();

  const statuses = [
    "",
    "accepted",
    "validating",
    "queued",
    "running",
    "streaming",
    "retry_wait",
    "cancel_requested",
    "succeeded",
    "failed",
    "cancelled",
    "expired",
  ];
  const types = ["", "chat", "deep_research"];
</script>

<section class="rounded-2xl border border-white/10 bg-black/20 p-3">
  <div class="grid gap-3 xl:grid-cols-[minmax(180px,1.3fr)_repeat(5,minmax(130px,0.8fr))_auto]">
    <label class="grid gap-1.5">
      <span class="text-[11px] font-black uppercase tracking-[0.14em] text-slate-500">Page-local job ID search</span>
      <input
        class="min-h-10 rounded-xl border border-white/10 bg-slate-950 px-3 text-sm outline-none focus:border-cyan-300/50"
        placeholder="job_..."
        bind:value={filters.search}
        {disabled}
      />
    </label>
    <label class="grid gap-1.5">
      <span class="text-[11px] font-black uppercase tracking-[0.14em] text-slate-500">Status</span>
      <select class="min-h-10 rounded-xl border border-white/10 bg-slate-950 px-3 text-sm outline-none focus:border-cyan-300/50" bind:value={filters.status} {disabled}>
        {#each statuses as status}
          <option value={status}>{status || "Any status"}</option>
        {/each}
      </select>
    </label>
    <label class="grid gap-1.5">
      <span class="text-[11px] font-black uppercase tracking-[0.14em] text-slate-500">Type</span>
      <select class="min-h-10 rounded-xl border border-white/10 bg-slate-950 px-3 text-sm outline-none focus:border-cyan-300/50" bind:value={filters.type} {disabled}>
        {#each types as type}
          <option value={type}>{type || "Any type"}</option>
        {/each}
      </select>
    </label>
    <label class="grid gap-1.5">
      <span class="text-[11px] font-black uppercase tracking-[0.14em] text-slate-500">Model</span>
      <input class="min-h-10 rounded-xl border border-white/10 bg-slate-950 px-3 text-sm outline-none focus:border-cyan-300/50" bind:value={filters.model} {disabled} />
    </label>
    <label class="grid gap-1.5">
      <span class="text-[11px] font-black uppercase tracking-[0.14em] text-slate-500">Account</span>
      <input class="min-h-10 rounded-xl border border-white/10 bg-slate-950 px-3 text-sm outline-none focus:border-cyan-300/50" bind:value={filters.account} {disabled} />
    </label>
    <label class="grid gap-1.5">
      <span class="text-[11px] font-black uppercase tracking-[0.14em] text-slate-500">Client request</span>
      <input class="min-h-10 rounded-xl border border-white/10 bg-slate-950 px-3 text-sm outline-none focus:border-cyan-300/50" bind:value={filters.client_request_id} {disabled} />
    </label>
    <div class="flex items-end gap-2">
      <button class="inline-flex min-h-10 items-center gap-2 rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-3 text-sm font-black text-cyan-100" onclick={onApply} {disabled}>
        <span aria-hidden="true">S</span>
        Apply
      </button>
      <button class="inline-flex min-h-10 items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 text-sm font-black text-slate-200" onclick={onClear} {disabled}>
        <span aria-hidden="true">X</span>
        Clear
      </button>
    </div>
  </div>
  <div class="mt-3 grid gap-3 md:grid-cols-[minmax(140px,0.5fr)_minmax(0,1fr)]">
    <label class="grid gap-1.5">
      <span class="text-[11px] font-black uppercase tracking-[0.14em] text-slate-500">Error code</span>
      <input class="min-h-10 rounded-xl border border-white/10 bg-slate-950 px-3 text-sm outline-none focus:border-cyan-300/50" bind:value={filters.error_code} {disabled} />
    </label>
    <p class="self-end text-xs leading-relaxed text-slate-500">
      Status, type, model, account, client request ID, and error code are server-side filters. Job ID search is local to the loaded page because the list endpoint does not ship a global search parameter.
    </p>
  </div>
</section>
