<script lang="ts">
  import { statusMeta } from "./formatting";
  import type { AgentJobStatus } from "./types";

  let { status }: { status?: AgentJobStatus | null } = $props();
  const meta = $derived(statusMeta(status));
  const icon = $derived(meta.label.slice(0, 1).toUpperCase());
  const classes = $derived(
    meta.tone === "ok"
      ? "border-emerald-300/30 bg-emerald-300/10 text-emerald-100"
      : meta.tone === "bad"
        ? "border-rose-300/35 bg-rose-300/10 text-rose-100"
        : meta.tone === "warn"
          ? "border-amber-300/35 bg-amber-300/10 text-amber-100"
          : "border-white/12 bg-white/[0.04] text-slate-200",
  );
</script>

<span class={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-black ${classes}`}>
  <span aria-hidden="true" class="grid h-4 w-4 place-items-center rounded-full border border-current/30 text-[10px]">{icon}</span>
  <span>{meta.label}</span>
</span>
