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

Credential setup workflow:

- Never ask the user to paste Pushover keys into chat, and never print values
  from `.pushover.env`.
- Use the bundled setup helper. It prompts in the terminal and writes
  `~/.codex/codex-notify/.pushover.env` with restrictive permissions.
- Run the helper in a PTY/interactive terminal so the user can type hidden
  values locally.
- If working from this repo checkout, run:

```bash
python3 plugins/codex-notify/tools/setup_pushover_credentials.py
```

- From an installed plugin, locate the helper with `rg --files` under the
  Codex plugin directories, then run the first path that ends in
  `codex-notify/.../tools/setup_pushover_credentials.py` or
  `codex-notify/tools/setup_pushover_credentials.py`.
- If the helper cannot be found, report that the installed plugin bundle looks
  incomplete and ask the user to reinstall Codex Notify. Do not fall back to
  collecting secrets in chat.
- If the credential file already exists, inspect only whether required keys are
  present. Use the helper's `--force` flag only when the user explicitly wants
  to replace existing credentials.
- After setup, report only the credential file path and the next dry-run/sample
  commands. Do not display secret values.

Never print secrets from env files, logs, or notification payloads. Use
`CODEX_PUSHOVER_SAMPLE=1` only when the user explicitly asks to send a sample
notification.
