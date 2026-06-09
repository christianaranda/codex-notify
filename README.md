# Codex Notify

Codex Notify is a Codex plugin that sends a notification when a Codex turn
finishes. It uses a plugin-bundled `Stop` lifecycle hook and sends a compact
notification with status, prompt summary, result summary, verification signals,
repository metadata, and an optional PR link. The `1.0.0-rc.1` release candidate
ships with a Pushover delivery provider.

Status: `1.0.0-rc.1` release candidate.

This is a community plugin distributed through a GitHub/repo marketplace. It is
not an OpenAI-curated plugin and is not listed in the public Codex Plugin
Directory.

## Why This Exists

Codex can run a long time, especially with /goal. It can finish when you're not
looking, maybe you're baking bread or cleaning your kitchen or otherwise enjoying
life. Instead of checking on Codex periodically, Codex Notify was built to solve
this by sending push notifications to your device with useful signal: what
finished, whether it needs attention, what was verified, which repo changed, and
whether there is a PR to open.

Enjoy life while your agents work without checking your computer or ChatGPT.

## What You Get

- A status-first notification: `Done` or `Needs attention`.
- A short prompt summary and result summary.
- Verification/test lines when Codex reports them.
- Repository, branch, short SHA, dirty state, model, host, and duration when
  available.
- GitHub PR links sent as native notification links when Codex reports a PR.
- Local SQLite notification history so you can review and improve message
  quality over time.

## Requirements

- Codex with plugin and hook support.
- Python 3.11 or newer available as `python3`.
- A Pushover account, user key, and application token.
- macOS is the tested platform for this release candidate. Focus suppression
  uses macOS System Events.

Hooks are enabled by default in current Codex builds. If you or your workspace
has disabled hooks, re-enable the canonical feature key:

```toml
[features]
hooks = true
```

Codex may require you to review and trust plugin-bundled hooks after install.
If Codex reports that hooks need review, open `/hooks`, inspect the command,
and trust it if it matches this plugin.

## Quick Start

1. Add the marketplace source:

```bash
codex plugin marketplace add christianaranda/codex-notify
```

2. Open the Codex plugin directory, install `Codex Notify`, and restart Codex.
   If Codex asks you to review hooks, run `/hooks`, inspect the command, and
   trust it if it points at this plugin.

3. Ask Codex to set up the Pushover credentials:

```text
Use Codex Notify to set up Pushover credentials on this Mac. Locate and run the bundled setup_pushover_credentials.py helper. Ask me to type the Pushover user key and app token into the terminal; do not ask me to paste secrets into chat.
```

The helper prompts in the terminal and creates:

```text
~/.codex/codex-notify/.pushover.env
```

If you are setting up from this checkout instead of an installed plugin, Codex
can run:

```bash
python3 plugins/codex-notify/tools/setup_pushover_credentials.py
```

Codex installs the plugin bundle, but hook-only plugins do not currently get a
generic provider-secret form. Codex Notify keeps using a simple local env file;
the setup helper creates it for you with restrictive file permissions.

What Codex should do for that setup prompt:

- Run the bundled helper in an interactive terminal.
- Ask you to type secrets into the terminal, not into chat.
- Create or update `~/.codex/codex-notify/.pushover.env`.
- Never print the credential values.
- Ask before replacing an existing credential file.

4. Run a dry-run turn. This proves the hook runs without sending to Pushover:

```bash
CODEX_NOTIFY_DRY_RUN=1 CODEX_NOTIFY=always codex exec \
  -c 'notify=[]' \
  --cd "$PWD" \
  "Reply exactly: dry run complete"
```

5. Send one explicit sample notification:

```bash
CODEX_PUSHOVER_SAMPLE=1 codex exec \
  -c 'notify=[]' \
  --cd "$PWD" \
  "Reply exactly: sample plugin notification sent"
```

You should now have one dry-run row in local history and one live Pushover
notification. If either step fails, start with `notify.log` and the
Troubleshooting section below.

## Local Development Install

From this checkout:

```bash
codex plugin marketplace add .
```

Then install `Codex Notify` from the Codex plugin directory and restart Codex.

## Configuration

Most users can start with the defaults. Add a config file only after the smoke
test works and you know what behavior you want to change.

Optional config can live at `~/.codex/codex-notify/config.toml`.

For local development from this checkout,
`plugins/codex-notify/config.example.toml` is a full template. See
`docs/configuration.md` for every setting and common recipes.

When installed, Codex also provides `PLUGIN_DATA`. The hook checks
`PLUGIN_DATA/config.toml` and `PLUGIN_DATA/.pushover.env` first, then falls
back to `~/.codex/codex-notify/`.

The stable fallback path is documented because the exact `PLUGIN_DATA` path is
managed by Codex and includes marketplace-specific naming. The setup helper
creates `~/.codex/codex-notify/.pushover.env`; use `pushover_env_path` or
`CODEX_PUSHOVER_ENV` only if you intentionally want to manage a custom path.

## Confirm It Worked

For dry runs, `notify.log` should contain `dry_run_publish` and `sent`. For live
sends, your Pushover app should receive the sample notification.

Installed-plugin logs live under a Codex plugin data directory shaped like:

```text
~/.codex/plugins/data/codex-notify-<marketplace>/notify.log
```

The exact suffix varies by marketplace name. The stable fallback path is:

```text
~/.codex/codex-notify/notify.log
```

The local history database lives next to the log as `notify_history.sqlite3`.

## Common Next Steps

- Too many notifications: set `default_policy = "long"` in `config.toml`.
- Need subagent notifications too: set `notify_subagents = true`.
- Want less content sent to Pushover: disable fields such as `include_task`,
  `include_git`, or `include_verification`.
- Want to review message quality: run `python3 tools/notification_history_server.py`
  and open `http://127.0.0.1:60605`.

## Behavior

- Handles Codex `Stop` hook payloads.
- Skips hook re-entry when `stop_hook_active` is true.
- Deduplicates by `turn_id` using SQLite.
- Defaults to `CODEX_NOTIFY=always`; supports `always`, `long`, and `none`.
- Supports `[notify]`, `[long-run]`, `[no-notify]`, and `[notify:none]`.
- Skips subagent completion notifications by default; set
  `notify_subagents = true` to opt in.
- Sends prompt, result, verification, repo/branch/SHA/dirty state, model, host,
  and duration when available.
- Sends GitHub PR links through Pushover's explicit `url` and `url_title`
  fields instead of leaking raw Markdown URLs into the body.
- Stores lightweight local notification history in SQLite by default so message
  quality can be reviewed and improved.
- Fails open: hook errors are logged and do not block Codex completion.
- Writes no stdout during normal hook operation.

## Data and Privacy

Codex Notify sends notification content to the configured delivery provider. In
this release candidate, that provider is Pushover. By default, the message can
include:

- A short summary of your latest prompt.
- A short summary of the assistant's final response.
- Detected verification/test lines.
- Repository name, branch, short SHA, dirty count, model, host, and duration.
- A GitHub PR URL/title when the assistant explicitly reports a PR.

This plugin stores local runtime data:

- `notify.log`: JSONL diagnostics.
- `notify_state.sqlite3`: duplicate-suppression state.
- `notify_history.sqlite3`: rendered notification title/body and metadata.
- `.pushover.env`: local Pushover credentials, normally created by the bundled
  setup helper.

It does not intentionally store raw transcript content, and it does not store
Pushover credentials in SQLite. Notification history does store the rendered
title/body unless `history_store_messages = false`.

For more detail, see `docs/privacy.md`.

## Local History Debug Page

Run a local browser for stored notification history:

```bash
python3 tools/notification_history_server.py
```

Open:

```text
http://127.0.0.1:60605
```

The page binds to `127.0.0.1` by default, reads the installed plugin history DB,
and supports search, filtering, sorting, column toggles, horizontal table
scrolling, and a rendered message preview.

## Troubleshooting

- No notification: confirm the plugin is installed and enabled, start a new
  thread after installing, and check whether Codex is asking you to review hooks
  with `/hooks`.
- Hooks disabled: make sure `[features].hooks` is not set to `false` by your
  user config, project config, or workspace requirements.
- Missing credentials: ask Codex to run the bundled
  `setup_pushover_credentials.py` helper, or run it from this checkout with
  `python3 plugins/codex-notify/tools/setup_pushover_credentials.py`.
- Dry run works but live send does not: check `notify.log` for Pushover API
  errors and confirm the user key/app token belong to the same Pushover account.
- Duplicate suppression: remove `notify_state.sqlite3` from the plugin data
  directory if you need to re-test the same captured turn id.
- Too many notifications: use `CODEX_NOTIFY=long`, `default_policy = "long"`,
  `include_cwds`, `exclude_cwds`, or prompt tags such as `[no-notify]`.
- Focus suppression not working: macOS may need Accessibility or Automation
  permission for the process running Codex hooks.

## Development

Validate manifests and Python:

```bash
python3 -c 'import json; [json.load(open(p)) for p in [
  ".agents/plugins/marketplace.json",
  "plugins/codex-notify/.codex-plugin/plugin.json",
  "plugins/codex-notify/hooks/hooks.json"
]]'
python3 -m py_compile \
  plugins/codex-notify/hooks/codex_notify.py \
  tools/notification_history_server.py \
  tests/test_notification_history_server.py
python3 -m unittest discover -s tests
```

Use `docs/release-checklist.md` before tagging or announcing a release.

## More Docs

- Need to tune notification behavior: `docs/configuration.md`.
- Need to understand what leaves your machine: `docs/privacy.md`.
- Need to confirm supported environments: `docs/compatibility.md`.
- Need release history: `CHANGELOG.md`.
- Maintaining or releasing the plugin: `docs/release-checklist.md`.
- Writing public launch copy: `docs/announcement-notes.md`.
- Reporting sensitive issues: `SECURITY.md`.
