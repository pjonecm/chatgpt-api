# opencode Integration

This integration uses opencode's custom local provider support.

The integration is intentionally a config/template layer. The core server does
not import opencode and opencode does not need a custom runtime package for the
first version.

## Start The Local API

Start the API with the saved accounts auto-discovered from
`secrets/accounts/*`:

```sh
CHATGPT_API_KEY=local-dev-key chatgpt-api serve --port 8000 --agent-mode optimized
```

Check the server:

```sh
curl http://127.0.0.1:8000/health
curl -H 'Authorization: Bearer local-dev-key' http://127.0.0.1:8000/v1/models
```

If you want to pin one local account alias for testing, use something explicit
such as `--account main-free`. Account names are aliases you created during
capture import, not automatic plan names.

## One-Time opencode Setup

Run the launcher with no arguments to open the opencode consumer setup:

```sh
bun integrations/opencode/chatgpt-opencode.mjs
```

This only writes or removes opencode config:

```text
~/.config/opencode/opencode.json
```

It asks for the Bridge API URL, bearer key, model, and optional opencode config
path. It does not configure accounts, server ports, concurrency, image output,
research output, or routing policy. Manage those in the API console.
After setup, keep the local API server running and open opencode normally:

```sh
opencode .
```

Non-interactive inject/eject/status for scripts:

```sh
bun integrations/opencode/opencode-config.mjs --inject \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key \
  --model chatgpt-web/auto@optimized

bun integrations/opencode/opencode-config.mjs --status \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key

bun integrations/opencode/opencode-config.mjs --eject \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key
```

For multi-account routing, configure accounts and runtime limits in the console
or start the server with `--accounts`:

```sh
CHATGPT_API_KEY=local-dev-key chatgpt-api serve \
  --accounts main-free,image-pro \
  --account-strategy failover \
  --port 8000 \
  --agent-mode optimized
```

## Configure opencode Manually

Copy `opencode.example.json` into your opencode config and set:

```sh
export CHATGPT_API_KEY=local-dev-key
```

Optional global install with Bun:

```sh
bun install -g opencode-ai
```

The provider points opencode at:

```text
http://127.0.0.1:8000/v1
```

## Run opencode As An Agent

Daily usage after setup should be plain opencode:

```sh
opencode .
```

If `opencode` is not installed on the machine:

```sh
bun install -g opencode-ai
```

Developer fallback: use the launcher. It writes a temporary opencode config with
`model` and `small_model` pinned to ChatGPT Web, then starts the interactive
opencode coding agent. There is no `run` subcommand here because `opencode
[project]` is the TUI agent mode.
The launcher also sets `OPENCODE_CONFIG_CONTENT`, so it can override an existing
project `opencode.json` that points at another provider.

```sh
bun integrations/opencode/chatgpt-opencode.mjs .
```

To start the agent in another project:

```sh
bun integrations/opencode/chatgpt-opencode.mjs /path/to/project
```

Raw opencode command, if you want to call opencode directly:

```sh
OPENCODE_CONFIG="$PWD/integrations/opencode/opencode.example.json" \
CHATGPT_API_KEY=local-dev-key \
bunx --bun opencode-ai --pure .
```

Use the launcher instead of the raw command if the project already has an
`opencode.json`; project config can override `OPENCODE_CONFIG`.

The launcher ultimately calls this shape internally:

```sh
bunx --bun opencode-ai --pure --model chatgpt-web/auto@optimized /path/to/project
```

Check what opencode sees before opening the TUI:

```sh
bun integrations/opencode/chatgpt-opencode.mjs --debug-config
```

The resolved config should include:

```json
"model": "chatgpt-web/auto@optimized",
"small_model": "chatgpt-web/auto@optimized"
```

The launcher defaults to base model `chatgpt-web/auto` plus `@optimized`
because ChatGPT Web may route around a temporary GPT-5.5 limit after retry. To
force explicit GPT-5.5 and surface model-limit errors, pass
`--model chatgpt-web/gpt-5-5`.

## Agent Prompt Modes

The server supports two bridge prompt profiles:

```text
optimized  compact bridge prompt for small tasks, POC work, refresh/copy/write jobs
opencode   fuller bridge prompt that preserves opencode's long agent context, skills, and tool docs
```

Pick per server:

```sh
CHATGPT_API_KEY=local-dev-key chatgpt-api serve --port 8000 --agent-mode optimized
CHATGPT_API_KEY=local-dev-key chatgpt-api serve --account image-pro --port 8000 --agent-mode opencode
```

Pick per opencode model:

```sh
bun integrations/opencode/chatgpt-opencode.mjs --agent-mode optimized .
bun integrations/opencode/chatgpt-opencode.mjs --agent-mode opencode .
```

Or call opencode directly with model suffixes:

```sh
bunx --bun opencode-ai --pure --model chatgpt-web/auto@optimized .
bunx --bun opencode-ai --pure --model chatgpt-web/auto@opencode .
```

Use `optimized` for quick local automation and free-account proof-of-concepts.
Use `opencode` when you want behavior closer to Codex/Claude style coding
agents and can tolerate heavier prompts.

The setup wizard stores this preference so normal opencode launches do not need
the long model suffix every time.

Keep `--dangerously-skip-permissions` out of real projects unless you
intentionally want opencode to auto-approve file edits and shell commands.

## Accounts, Limits, Images, And Attachments

See `docs/OPENCODE_AGENT_ROADMAP.md` for the public plan. Current behavior:

- Single-account mode: use `--account main-free`.
- Multi-account mode: use `--accounts main-free,image-pro --account-strategy failover`.
- Use `chatgpt-web/auto@optimized` when you want ChatGPT Web to fall back like
  the browser after a model limit.
- Use an explicit model such as `chatgpt-web/gpt-5-5@optimized` when you want
  limit errors to show up clearly in opencode.
- ChatGPT image generation is available through `/v1/images/generations` and
  `python3 -m chatgpt_api api image`.
- Image requests are saved to disk. If the user names a path, that path is used;
  otherwise files go under the configured image output directory and the
  assistant response includes the saved path.
- Image failover avoids retrying another account after ChatGPT appears to have
  completed an image task but the bridge cannot see the asset yet. This prevents
  duplicate generations across accounts.
- The opencode chat adapter does not automatically convert attached local files
  into bridge image uploads yet. For image generation, image edit, OCR, or
  multi-image composite work, call the bridge image/vision endpoints or CLI
  commands directly and pass the produced paths back into opencode.
- For normal code work, pass local paths in the prompt and let opencode tools
  read, grep, or inspect those files.

## Automated Smoke Tests

Use `run` only for non-interactive smoke tests or CI. It is not the normal agent
entrypoint.

For a no-install Bun smoke test:

```sh
mkdir -p /tmp/chatgpt-api-opencode-smoke
OPENCODE_CONFIG=./integrations/opencode/opencode.example.json \
CHATGPT_API_KEY=local-dev-key \
bunx --bun opencode-ai run --pure --dir /tmp/chatgpt-api-opencode-smoke \
  --model chatgpt-web/auto \
  "ตอบแค่ ok"
```

To test file-edit tools safely, run opencode inside a throwaway directory:

```sh
mkdir -p /tmp/chatgpt-api-opencode-smoke
OPENCODE_CONFIG="$PWD/integrations/opencode/opencode.example.json" \
CHATGPT_API_KEY=local-dev-key \
bunx --bun opencode-ai run --pure --dir /tmp/chatgpt-api-opencode-smoke \
  --model chatgpt-web/auto --dangerously-skip-permissions \
  "Create a file named hello.txt in the current directory containing exactly sawasdee."
```

Avoid running multiple opencode commands against the same local opencode data
directory at the same time; opencode uses a local database and concurrent runs
can fail with `database is locked`.

## Model Aliases

The compatibility server maps friendly model IDs to ChatGPT Web payloads:

```text
auto                            -> auto
auto@optimized                  -> auto + optimized bridge prompt
auto@opencode                   -> auto + full opencode bridge prompt
gpt-5-5                         -> gpt-5-5
gpt-5-5@optimized               -> gpt-5-5 + optimized bridge prompt
gpt-5-5@opencode                -> gpt-5-5 + full opencode bridge prompt
gpt-5-5-thinking-standard       -> gpt-5-5-thinking + thinking_effort=standard
gpt-5-5-thinking-standard@...   -> same model/effort + selected bridge prompt
gpt-5-5-thinking-extended       -> gpt-5-5-thinking + thinking_effort=extended
gpt-5-5-thinking-max            -> gpt-5-5-thinking + thinking_effort=max
gpt-5-5-pro-standard            -> gpt-5-5-pro + thinking_effort=standard
gpt-5-5-pro-extended            -> gpt-5-5-pro + thinking_effort=extended
```

Free accounts should use `gpt-5-5` for explicit GPT-5.5, or `auto` when you
want ChatGPT Web to choose a fallback model the way the web UI does after a
retry.

If an explicit model hits a web-side limit or is not available, the API returns
an OpenAI-style error with a readable `code`, for example
`chatgpt_model_limit` or `chatgpt_empty_response`, and a message suggesting
`chatgpt-web/auto`. When ChatGPT exposes reset metadata through
`/backend-api/conversation/init`, the error also includes fields such as
`chatgpt_model_limit.resets_after` so opencode can show why the model did not
answer.

## Tool Calls

opencode sends OpenAI-shaped `tools` to `/v1/chat/completions`.

The server asks ChatGPT to plan tool calls as strict JSON, validates that the
requested tool name exists in the request, and returns OpenAI-style `tool_calls`.
opencode remains responsible for executing file reads, file writes, patches,
shell commands, approvals, and workspace safety.

That split is deliberate. It keeps this project from becoming a file-editing
agent with its own sandbox rules.
