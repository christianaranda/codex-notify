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

Credential setup:

- Never ask the user to paste Pushover keys into chat.
- Prefer the bundled setup helper. It prompts in the terminal and writes
  `~/.codex/codex-notify/.pushover.env` with restrictive permissions.
- From this repo checkout, run:

```bash
python3 plugins/codex-notify/tools/setup_pushover_credentials.py
```

- From an installed plugin, locate `setup_pushover_credentials.py` under the
  installed `codex-notify` plugin bundle and run it with `python3`.
- If the credential file already exists, inspect only whether required keys are
  present. Do not print values. Use the helper's `--force` flag only when the
  user explicitly wants to replace existing credentials.

Never print secrets from env files, logs, or notification payloads. Use
`CODEX_PUSHOVER_SAMPLE=1` only when the user explicitly asks to send a sample
notification.
