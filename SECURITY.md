# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| `1.0.0-rc.1` | Yes, release-candidate support |
| Earlier development commits | No |

## Reporting a Vulnerability

Do not open a public issue for secrets, credential exposure, or vulnerabilities
that could compromise users.

Use GitHub private vulnerability reporting if it is enabled for the repository.
If it is not enabled, contact the maintainer through a private channel and share
only the minimum detail needed to start triage.

## What to Redact

Before sharing logs, config, screenshots, or SQLite rows, redact:

- `PUSHOVER_USER_KEY`
- `PUSHOVER_APP_TOKEN`
- Pushover request IDs if you consider them sensitive
- Private repository names or branch names
- Prompt/result content that contains proprietary or personal information
- Local filesystem paths if they reveal sensitive project names

`notify.log` and `notify_history.sqlite3` can contain rendered notification
content. Treat them as private by default.

## Local Credentials

Credentials should live in `.pushover.env` under `PLUGIN_DATA` or
`~/.codex/codex-notify/`. Codex does not create this provider credential file
for you; create it locally on each machine that should send notifications. Do
not commit this file.

If credentials are accidentally committed or shared, rotate the Pushover app
token and/or user key immediately.
