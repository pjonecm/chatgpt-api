# CLI

`chatgpt-api` is the operator CLI for the local ChatGPT Web Bridge.

Use the module command in docs and automation:

```sh
python3 -m chatgpt_api <command>
```

If your shell can find the installed console script, this shorter form is also
valid:

```sh
chatgpt-api <command>
```

It has three layers:

- local capture tools that inspect account files without starting the API
- `server` commands that launch the main API
- `admin` commands that manage a running API server

## First Checks

```sh
python3 -m chatgpt_api doctor
python3 -m chatgpt_api doctor --json
python3 -m chatgpt_api menu
python3 -m chatgpt_api
```

`doctor` checks Python version, local account capture profiles, Docker files,
`/health`, and `/v1/models`.

Running the CLI with no arguments in an interactive terminal opens the
same control menu. Non-interactive shells and Docker/CI should use explicit
subcommands.

Example JSON shape:

```json
{
  "object": "chatgpt.doctor",
  "ok": true,
  "base_url": "http://127.0.0.1:8000/v1",
  "api_key": "<set>",
  "checks": [
    {"name": "python", "ok": true, "detail": "3.12.0"},
    {"name": "account_profiles", "ok": true, "detail": "2 profile(s) in secrets/accounts"}
  ]
}
```

## Start The API

`--account` and `--accounts` take local account names. Those names are aliases
you choose when saving captures, for example `free-main`, `pro-main`, or
`work-pro`. They are not automatic plan selectors.

Recommended local command:

```sh
python3 -m chatgpt_api server start \
  --accounts free-main,pro-main \
  --account-strategy failover \
  --api-key local-dev-key \
  --host 127.0.0.1 \
  --port 8000 \
  --public-base-url http://127.0.0.1:8000/v1
```

LAN command:

```sh
python3 -m chatgpt_api server start \
  --accounts free-main,pro-main \
  --account-strategy failover \
  --api-key local-dev-key \
  --host 0.0.0.0 \
  --port 8000 \
  --public-base-url http://192.168.1.203:8000/v1
```

Print a preset without starting:

```sh
python3 -m chatgpt_api server command --preset local
python3 -m chatgpt_api server command --preset lan
python3 -m chatgpt_api server command --preset docker
```

`chatgpt-api serve` is still supported and accepts the same server flags.

Fully interactive launch:

```sh
python3 -m chatgpt_api server start --interactive
```

The interactive launch asks for account aliases, routing strategy, host, port,
Bearer key, public download URL, prompt mode, fallback policy, privacy mode,
concurrency limits, output directories, and admin DB path before starting the
API.

## Runtime Admin

All admin commands talk to a running API server.

```sh
python3 -m chatgpt_api admin status --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
python3 -m chatgpt_api admin capacity --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
python3 -m chatgpt_api admin models --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
python3 -m chatgpt_api admin usage --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
```

Use `--json` for stable machine output:

```sh
python3 -m chatgpt_api admin capacity --json --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
```

## Account Management

List accounts known by the running API:

```sh
python3 -m chatgpt_api admin accounts --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
python3 -m chatgpt_api admin account list --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
```

Live-check all accounts:

```sh
python3 -m chatgpt_api admin check-accounts --account all --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
python3 -m chatgpt_api admin account verify --account all --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
```

Add or refresh an account from copied browser request details. The CLI first
inspects the capture, refuses to save if required or recommended checks fail,
then live-checks the account after saving.

```sh
python3 -m chatgpt_api admin account add \
  --account pro-main \
  --capture-file ./chatgpt-request.txt \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key
```

The same flow can be fully interactive:

```sh
python3 -m chatgpt_api menu
```

Or paste a capture without preparing a file:

```sh
python3 -m chatgpt_api admin account add --paste \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key
```

The CLI will ask for the account name and then accept pasted headers plus
payload, or a full `Copy as cURL` command, until a line containing only
`END_CAPTURE`.

Update an existing account after tokens/cookies expire:

```sh
python3 -m chatgpt_api admin account update \
  --account pro-main \
  --capture-file ./chatgpt-request.txt \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key
```

`save-capture` remains as an alias-style command and uses the same validation
and live-verify flow.

Account names should be ASCII slugs such as `free-main`, `pro-main`,
`free-2`, or `team-main`.

Delete an account capture and settings:

```sh
python3 -m chatgpt_api admin account delete \
  --account old-free-main \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key
```

The older `admin delete-account` command is still available.

## Limits

Recommended local defaults:

```sh
python3 -m chatgpt_api admin set-limits \
  --chat free=1,go=2,plus=3,pro=4 \
  --upload free=1,go=1,plus=1,pro=1 \
  --image free=1,go=1,plus=2,pro=3 \
  --research free=1,go=1,plus=2,pro=2 \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key
```

You can raise limits, but ChatGPT Web may still apply hidden short rate limits,
especially for image and research bursts.

`--upload` controls source-image work shared by OCR, image description, image
edits, and multi-image composite requests. Keep the default `1` unless you have
tested the account under load.

## Artifacts

List generated images and Deep Research reports:

```sh
chatgpt-api admin artifacts --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
```

Delete metadata only:

```sh
chatgpt-api admin delete-artifact --file-id <id> --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
```

Delete metadata and file:

```sh
chatgpt-api admin delete-artifact --file-id <id> --delete-file --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
```

Download files through:

```text
GET /v1/chatgpt/files/{file_id}/{filename}
```

Use returned `download_url` for browsers or LAN clients. Use returned local
`path` only when the client can access the same filesystem.

## Smoke Tests

Chat:

```sh
chatgpt-api admin test-chat \
  --message "Reply with exactly: bridge ok" \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key
```

Image:

```sh
chatgpt-api admin test-image \
  --prompt "simple blue app icon, no text" \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key local-dev-key
```

Vision / OCR without starting a separate client:

```sh
chatgpt-api vision \
  --mode ocr \
  --input-image ./favicon.png \
  --prompt "Extract visible letters only"
```

Structured OCR with approximate bounding boxes:

```sh
chatgpt-api vision \
  --mode ocr \
  --input-image ./panel.png \
  --prompt 'Return strict JSON only. Schema: {"items":[{"text":"string","bbox":{"x":0,"y":0,"w":0,"h":0},"confidence":"low|medium|high"}]}. Use pixel coordinates relative to the input image. Estimate boxes when exact layout is uncertain.'
```

The CLI prints the model response. If you ask for JSON, parse stdout as model
JSON, but remember that boxes are estimated by ChatGPT rather than returned from
a native OCR layout engine.

Image edit with one source image:

```sh
chatgpt-api image \
  --prompt "Change the icon letters to FW while preserving the same style" \
  --input-image ./favicon.png \
  --aspect-ratio 1:1
```

Image composite with multiple source images:

```sh
chatgpt-api image \
  --prompt "Combine these references into one manga cover image" \
  --input-image ./character.png \
  --input-image ./background.png \
  --input-image ./logo.png \
  --aspect-ratio 3:4
```

The CLI accepts at most 10 input images per request. Image edit/composite
returns one final image. Supported ratios are `auto`, `1:1`, `3:4`, `9:16`,
`4:3`, and `16:9`.

Important: source images should already match one of those ratios if you need
layout and object positions to stay stable. `auto` with an unusual ratio can
produce a different canvas size.

Models:

```sh
chatgpt-api admin models --json --base-url http://127.0.0.1:8000/v1 --api-key local-dev-key
```

## Raw Local Capture Tools

These do not need the API server:

```sh
chatgpt-api accounts
chatgpt-api inspect-capture --account pro-main
chatgpt-api account-info --account pro-main
chatgpt-api account-capabilities --account pro-main
chatgpt-api account-limits --account pro-main
chatgpt-api account-models --account pro-main
chatgpt-api account-check --account pro-main
```
