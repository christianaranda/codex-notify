# Plugin Implementation Plan

Status: historical implementation plan, updated for the `1.0.0-rc.1` release
candidate. Use `README.md` for install instructions and `docs/release-checklist.md`
for release gates.

## Decision

The public version is a Codex plugin that owns a `Stop` lifecycle hook. It does
not use the old top-level `notify = [...]` configuration path and does not shell
out to `curl`.

The original direct notifier was moved out of the public repo shape and kept
only in ignored local backup files during migration.

## Target Shape

```text
codex-notify/
  .codex-plugin/plugin.json
  hooks/
    hooks.json
    codex_notify.py
  skills/
    codex-notify/
      SKILL.md
  config.example.toml
  examples/
    pushover.env.example
  tests/
```

Runtime flow:

```text
Codex Stop hook payload
  -> event adapter
  -> optional transcript enrichment
  -> policy
  -> formatter
  -> Pushover provider
  -> local SQLite state/history
```

## Completed

- Plugin manifest and repo-local marketplace entry.
- Plugin-bundled `Stop` hook resolved through `PLUGIN_ROOT`.
- Pushover delivery through Python `urllib`.
- Fail-open hook behavior with local diagnostics.
- Config and credentials under `PLUGIN_DATA` with stable fallback to
  `~/.codex/codex-notify/`.
- SQLite duplicate suppression.
- SQLite notification history for reviewing rendered notifications.
- Local notification history debug page.
- Subagent notification opt-in.
- Long-run policy and prompt tags.
- Focus suppression on macOS.
- Prompt/result/verification/repo-rich notification formatting.
- GitHub PR URL extraction into Pushover's explicit URL fields.
- Markdown cleanup for Pushover bodies.
- Old history-schema migration.
- Dedupe lock release on publish failure.
- Unit tests for core behavior and debug history API behavior.
- CI for manifest parsing, Python compilation, and unit tests.

## Current Release Candidate Work

The `1.0.0-rc.1` release candidate is intended to prove that a public GitHub
repo marketplace install works cleanly for users outside the original local
environment.

Release candidate gates:

- Clean install from a GitHub marketplace source.
- Hook trust/review flow documented and verified.
- Dry run works before Pushover credentials.
- Live sample works after Pushover credentials.
- Public docs explain data sharing and local storage.
- Issues templates and security contact are present.
- Changelog describes the release candidate.

## Design Constraints

- Keep Pushover credentials local and out of plugin manifests, logs, and
  SQLite history.
- Keep stdout reserved for the Codex hook protocol; diagnostics go to
  `notify.log`.
- Keep network delivery bounded by hook timeout.
- Do not block Codex completion when notification delivery fails.
- Treat notification history as local debugging data; users can disable stored
  message bodies with `history_store_messages = false`.
- Avoid promising OpenAI-curated distribution. This is a community plugin
  distributed through a GitHub/repo marketplace unless/until that changes.

## Future Work

- Split the single hook script into smaller modules once the plugin interface
  stabilizes further.
- Add screenshots or a short demo GIF for public posts.
- Test more surfaces explicitly: Codex app, CLI, IDE extension, and supported
  operating systems.
- Add richer local history filters and export helpers if the SQLite history
  proves valuable.
- Consider optional notification sounds/priority only after the core message
  content is stable.
