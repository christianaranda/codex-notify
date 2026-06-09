---
name: codex-notify
description: Inspect and test the Codex Notify hook, including proof logs, dry runs, credential checks, and notification policy.
---

# Codex Notify

Use this skill when the user asks about Codex Notify, notification
configuration, missed notifications, duplicate suppression, dry runs, or test
sends.

The hook prefers the plugin-provided data directory:

```text
PLUGIN_DATA/
```

It also supports this stable fallback path:

```text
~/.codex/codex-notify/
```

Important files:

```text
config.toml
.pushover.env
notify.log
notify_state.sqlite3
```

Never print secrets from env files, logs, or notification payloads. Use
`CODEX_PUSHOVER_SAMPLE=1` only when the user explicitly asks to send a sample
notification.
