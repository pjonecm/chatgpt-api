<script lang="ts">
  import { typeLabel } from "./formatting";

  let { type }: { type?: string | null } = $props();
</script>

<span class="inline-flex items-center gap-1.5 rounded-full border border-cyan-300/25 bg-cyan-300/[0.07] px-2.5 py-1 text-xs font-black text-cyan-100">
  <span aria-hidden="true" class="grid h-4 w-4 place-items-center rounded-full border border-current/30 text-[10px]">{type === "deep_research" ? "R" : "C"}</span>
  <span>{typeLabel(type)}</span>
</span>
