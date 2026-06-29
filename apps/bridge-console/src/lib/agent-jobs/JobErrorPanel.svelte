<script lang="ts">
  import { redactValue } from "./formatting";
  import type { JobError } from "./types";

  let {
    error,
    uiFailure,
  }: {
    error?: JobError | null;
    uiFailure?: { code?: string; message?: string } | null;
  } = $props();
</script>

{#if error?.code || uiFailure?.message}
  <div class="rounded-2xl border border-rose-300/25 bg-rose-300/10 p-4">
    <div class="flex items-start gap-3">
      <span class="mt-0.5 grid h-5 w-5 place-items-center rounded-full border border-rose-200/40 text-xs font-black text-rose-100" aria-hidden="true">!</span>
      <div class="min-w-0">
        <h3 class="text-sm font-black uppercase tracking-[0.12em] text-rose-100">
          {error?.code ? "Job error" : "UI or network error"}
        </h3>
        <div class="mt-3 grid gap-2 text-sm">
          {#if error?.code}
            <div><span class="text-rose-200/70">Code:</span> <code>{error.code}</code></div>
            <div class="break-words text-rose-50">{String(redactValue(error.message || ""))}</div>
          {/if}
          {#if uiFailure?.message}
            <div><span class="text-rose-200/70">UI fetch:</span> <code>{uiFailure.code || "request_failed"}</code></div>
            <div class="break-words text-rose-50">{String(redactValue(uiFailure.message))}</div>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}
