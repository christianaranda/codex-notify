# Privacy and Local Data

Codex Notify is a local Codex plugin that sends selected turn-completion
information to a configured delivery provider. The `1.0.0-rc.1` provider is
Pushover. This document describes what leaves your machine and what is stored
locally.

## Plain-English Summary

- Codex Notify runs locally as a Codex hook.
- Notification text is sent to Pushover so Pushover can deliver it to your
  devices.
- Pushover credentials stay in your local `.pushover.env` file.
- Local SQLite history is enabled by default so you can inspect notification
  quality later.
- You can reduce sent fields, keep history metadata only, or disable history
  entirely with `config.toml`.

## Data Sent to Pushover

By default, each sent notification can include:

- Notification status: `Done` or `Needs attention`.
- Turn duration.
- A short summary of the latest user prompt.
- A short summary of the assistant's final response.
- Detected verification/test lines.
- Repository name, branch, short SHA, dirty count, model, host, and duration
  when available.
- A GitHub PR URL/title when the assistant explicitly reports a PR.

The plugin sends this data to Pushover using Pushover's message API. Pushover's
terms, privacy policy, retention, and device-delivery behavior apply after the
message is sent.

## Data Stored Locally

Runtime files normally live under the plugin data directory provided by Codex:

```text
PLUGIN_DATA/
```

The stable fallback path is:

```text
~/.codex/codex-notify/
```

Files:

- `.pushover.env`: local Pushover credentials.
- `config.toml`: optional local plugin configuration.
- `notify.log`: JSONL diagnostics.
- `notify_state.sqlite3`: duplicate-suppression state keyed by Codex turn id.
- `notify_history.sqlite3`: local notification history for reviewing message
  quality.

`notify_history.sqlite3` stores rendered notification title/body and metadata by
default. It does not intentionally store raw transcript content or Pushover
credentials.

## Reduce Stored Content

Disable notification history entirely:

```toml
history_enabled = false
```

Keep history metadata but do not store rendered title/body:

```toml
history_store_messages = false
```

Shorten retention:

```toml
history_retention_days = 14
```

Keep all rows:

```toml
history_retention_days = 0
```

## Reduce Sent Content

Use these settings in `config.toml`:

```toml
include_task = false
include_verification = false
include_git = false
include_model = false
include_host = false
```

You can also replace the default message template:

```toml
message_template = "{status}: {scope} finished in {duration}"
```

## Local Debug Page

The debug page binds to `127.0.0.1` by default:

```bash
python3 tools/notification_history_server.py
```

It reads `notify_history.sqlite3` and renders stored messages in your browser.
Do not bind it to a public interface unless you understand the data in your
history database and have your own access controls in place.

## Credentials

Do not commit `.pushover.env`. The repo `.gitignore` excludes `.pushover.env`,
`notify.log`, and `*.sqlite3`.

If you accidentally commit or share Pushover credentials, revoke and rotate the
Pushover application token and/or user key immediately.
