# Fast Jev compaction on Codex

Status: Codex plugin `fast-jev-codex@personal` is installed; both hooks were reviewed/trusted in the Codex CLI, and `features.hooks` is enabled. At the user's direction, `TYPESAFE_API_KEY` is configured at Windows user scope. The already-running Codex process has not reloaded it; restart Codex before the hook can use it.

## What the existing package does

`%USERPROFILE%\plugins\harness\vendor\fast-jev-compaction` is MIT-licensed source for a Claude Code hook and an npm library. It expects Claude's `session.compact` hook to return a rewritten message list. It sends Jev the conversation text and tool-call inputs; it replaces tool-result bodies with short length notes. It makes one or more HTTPS requests to `https://api.typesafe.ai/v1/systemone`. The package does not currently compact the active Codex transcript.

The original checkout is not install-ready: root `package.json` says `0.2.0`, `package-lock.json` says `0.1.0`, and `.claude-plugin/plugin.json` says `0.3.0`. I left it unchanged. The Codex plugin uses an isolated MIT-licensed copy of the core at commit `e3f262a7f4d42bd8dd32ced30d26176f7cb545b0`; its copied package/lock roots are aligned at `0.2.0` without changing pinned dependency versions.

## What a Codex adaptation can do

Official Codex docs list `PreCompact`, `PostCompact`, and `SessionStart(source="compact")` hooks. A `PreCompact` hook can read `transcript_path` and continue or stop compaction; it has no output field for replacing the transcript. The same docs warn that transcript format is not a stable hook interface. A `SessionStart(source="compact")` hook can add `additionalContext` after Codex's built-in compaction.

A Codex adaptation now uses `PreCompact` to compact eligible tool records into a bounded local sidecar, then `SessionStart(source="compact")` adds that sidecar to the immediate continuation. It supplements built-in compaction; it does not replace the Codex compactor as the Claude package does. Transcript parsing is best-effort and fails open when the schema changes.

## Data and activation boundary

Using Jev would transmit the current session's user/assistant text and tool-call arguments to TypeSafe. The library omits the full tool-result bodies in its Jev state, but counts and result decisions are still sent; kept records may be carried back as additional context. Do not embed the API key in a manifest or source file. The hook should require a securely configured `TYPESAFE_API_KEY`, preserve recent messages, cap request size/time, fail open, and log only counts and decision metadata.

The user authorized sending session text and tool-call arguments to TypeSafe Jev. The API key is stored only in the Windows user environment; the project, plugin manifest and source contain no key. The current Codex process still lacks the user-scope update, so its hooks have not read or transmitted a transcript. Restart Codex to load the new environment. The game client and Rust server never receive the Jev key and make no TypeSafe requests.

Verification: plugin schema validation passed; isolated core build passed; 29 upstream tests passed; Codex parser/sidecar self-test passed; `/hooks` showed one active PreCompact and one active SessionStart handler. No live Jev request, token/cost measurement, or current-session compaction was performed; enabling the user-scope credential still requires a Codex restart. No prompt cache affinity is configured. Current official docs: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Codex plugin packaging](https://developers.openai.com/plugins/build/plugins), and [submitting Claude Code plugins to OpenAI](https://developers.openai.com/plugins/guides/submit-claude-plugin).
