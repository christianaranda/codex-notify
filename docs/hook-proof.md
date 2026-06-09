# Hook Proof Notes

Date: 2026-05-03

Status: historical proof notes. These notes record what was learned while
building the plugin. They are not current install instructions. Use `README.md`
and `docs/release-checklist.md` for current user-facing setup.

Codex build tested at the time:

```text
Codex Desktop/0.128.0-alpha.1
macOS 26.4.0 arm64
```

## What Was Proven

- A repo-local plugin marketplace can expose this plugin to Codex.
- The app-server plugin install flow can install and enable the plugin without
  hand-editing plugin config.
- Plugin-bundled `Stop` hooks can run from an installed plugin cache.
- `Stop` hook commands run from the session cwd.
- Relative hook commands resolve from the session cwd, not from the plugin root.
- Codex provides `PLUGIN_ROOT` and `PLUGIN_DATA` to plugin hook commands.
- A hook command can use `PLUGIN_ROOT` to run packaged code from the installed
  plugin cache.
- A `Stop` hook that exits non-zero can cause Codex to continue the turn with
  the hook failure as a new prompt.

Current Codex documentation says hooks are enabled by default, uses `hooks` as
the canonical feature key, and routes plugin-bundled hooks through the same hook
trust-review flow as other non-managed hooks.

## Observed Stop Payload

The observed `Stop` payload included:

```json
{
  "session_id": "...",
  "turn_id": "...",
  "transcript_path": "~/.codex/sessions/...",
  "cwd": "<session cwd>",
  "hook_event_name": "Stop",
  "model": "gpt-5.5",
  "permission_mode": "bypassPermissions",
  "stop_hook_active": false,
  "last_assistant_message": "plugin hook proof fixed"
}
```

The payload was enough for the notification event model:

- `session_id` and `turn_id` for dedupe.
- `cwd` for scope.
- `model` for metadata.
- `last_assistant_message` for notification summary.
- `transcript_path` for optional enrichment.
- `stop_hook_active` for continuation/re-entry protection.

## Installed Paths

The installed plugin cache path followed this shape:

```text
~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/
```

The plugin data path followed this shape:

```text
~/.codex/plugins/data/<plugin>-<marketplace>/
```

Example from the proof:

```text
PLUGIN_ROOT=~/.codex/plugins/cache/<marketplace>/codex-notify/<version>
PLUGIN_DATA=~/.codex/plugins/data/codex-notify-<marketplace>
```

## Design Consequences

- The production hook must resolve packaged code through `PLUGIN_ROOT`.
- Runtime config, logs, and state should prefer `PLUGIN_DATA`, with a documented
  fallback to `~/.codex/codex-notify/`.
- The hook must catch all errors, write diagnostics to a file, and exit `0`
  with no stdout during normal operation.
- The event adapter should be built around the observed `Stop` payload.
- The public plugin path should not depend on the legacy top-level
  `notify = [...]` payload.
- User-facing docs should cover hook review/trust rather than old pre-release
  feature aliases.
