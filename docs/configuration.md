# Configuration Reference

Start here after the README quick start works. The defaults are intended to be
useful without a config file; add configuration only for the behavior you want
to change.

The stable user-facing config path is:

```text
~/.codex/codex-notify/config.toml
```

When Codex provides `PLUGIN_DATA`, the hook first checks:

```text
PLUGIN_DATA/config.toml
```

It then falls back to the stable path above. Use
`plugins/codex-notify/config.example.toml` as a full template.

Secrets live separately in `.pushover.env`:

```env
PUSHOVER_USER_KEY=
PUSHOVER_APP_TOKEN=
```

See `docs/privacy.md` for what is sent to Pushover, what is stored locally, and
which settings reduce stored or sent content.

## Common Recipes

Only notify for longer runs:

```toml
default_policy = "long"
long_run_seconds = 300
```

Notify for longer runs and failed-looking results:

```toml
default_policy = "long"
notify_on_failure = true
```

Keep main-thread notifications, but also notify when subagents finish:

```toml
notify_subagents = true
```

Reduce what leaves your machine:

```toml
include_task = false
include_verification = false
include_git = false
include_model = false
include_host = false
```

Keep local history metadata without storing rendered message bodies:

```toml
history_store_messages = false
```

Turn off local notification history:

```toml
history_enabled = false
```

Force or suppress one notification from a prompt:

```text
[notify]
[no-notify]
```

## Policy

| Setting | Default | Purpose |
| --- | --- | --- |
| `enabled` | `true` | Master on/off switch. |
| `default_policy` | `"always"` | Main policy: `always`, `long`, or `none`. |
| `notify_on_failure` | `false` | Under `long`, optionally notify when the assistant outcome looks blocked or failed. Keep this `false` to enforce the time boundary strictly. |
| `notify_subagents` | `false` | Notify for subagent thread completion. Main user threads are always eligible. |
| `long_run_seconds` | `300` | Minimum duration for `default_policy = "long"`. |
| `always_tags` | `["[notify]", "[long-run]"]` | Prompt tags that force a notification. |
| `skip_tags` | `["[no-notify]", "[notify:none]"]` | Prompt tags that suppress a notification. |
| `include_cwds` | `[]` | If non-empty, only notify for matching workspace path prefixes. |
| `exclude_cwds` | `[]` | Never notify for matching workspace path prefixes. |

`skip_tags` win over failure detection and forced-send tags.

## Message Formatting

| Setting | Default | Purpose |
| --- | --- | --- |
| `max_title_chars` | `160` | Pushover title truncation limit, capped at Pushover's 250-character limit. |
| `max_message_chars` | `1024` | Pushover body truncation limit, capped at Pushover's 1024-character limit. |
| `max_outcome_chars` | `560` | Assistant-summary truncation limit before templating. |
| `max_task_chars` | `220` | Latest user prompt truncation limit before templating. |
| `task_summary_mode` | `"local"` | Task summary mode: `local` uses the built-in compact summary; `codex` tries local `codex exec` and falls back locally; `auto` is an alias for Codex-first behavior; `off` keeps the cleaned prompt text. |
| `task_summary_max_chars` | `120` | Summary cap for the `{prompt}` / `{task}` field when summarization is enabled. |
| `task_summary_codex_command` | `""` | Optional path/name for the Codex CLI. Empty means try `codex`, then the bundled macOS app path. |
| `task_summary_codex_model` | `""` | Optional model override for the summary `codex exec`. Empty means use your Codex default. |
| `task_summary_timeout_seconds` | `8` | Timeout for the Codex summary call before falling back locally. |
| `max_verification_chars` | `180` | Verification/test-summary truncation limit before templating. |
| `fallback_scope_label` | `"workspace"` | Scope label when Codex does not provide a cwd. |
| `title_template` | `"{headline}"` | Title template. |
| `message_template` | `"{details}"` | Body template. |
| `include_duration` | `true` | Include duration in `{meta}`. |
| `include_host` | `true` | Include host name in `{meta}`. |
| `include_model` | `true` | Include Codex model in `{meta}` when provided. |
| `include_task` | `true` | Include the cleaned latest user prompt as `{prompt}` / `{task}` and in `{details}`. |
| `include_verification` | `true` | Include detected test/verification lines as `{verification}` and in `{details}`. |
| `include_git` | `true` | Include local Git repo, branch, short SHA, and dirty count when available. |
| `git_check_timeout_seconds` | `1` | Per-command timeout for local Git metadata collection. |
| `pushover_html` | `true` | Send `html=1` and render default detail labels with limited Pushover HTML. |

Available template placeholders:

```text
{status}
{status_styled}
{scope}
{headline}
{duration}
{duration_seconds}
{host}
{model}
{meta}
{outcome}
{prompt}
{task}
{verification}
{details}
{repo}
{branch}
{git_sha}
{git_dirty}
{git_changed_count}
{git_root}
{pr}
{cwd}
{session_id}
{turn_id}
{permission_mode}
{thread_source}
{subagent_name}
{originator}
```

Unknown placeholders render as empty strings, and invalid template syntax falls
back to the default template.

The default title now packs status, repo/scope, branch, and duration into
`{headline}`. The default body uses `{details}`, a structured block with labels
for status, prompt, result, verification, repo, runtime, and PR when those values
are available. When `pushover_html = true`, Pushover renders those labels in
bold and colorizes the status in the app detail view; mobile notification
previews may strip the styling.
The default detail block is fitted before delivery by shrinking long fields and
dropping lower-priority lines instead of cutting the final line mid-word.
Generated body truncation does not add an ellipsis; fields are shortened at word
boundaries or dropped so the notification does not end with a dangling fragment.

Task summaries are intentionally short and do not require API keys. The default
local summarizer is used because a nested `codex exec` has non-trivial startup
and token cost. If `task_summary_mode = "codex"` or `"auto"`, the hook invokes
`codex exec` through your existing Codex login/account, writes no session files,
disables Codex/plugin hooks for that nested run, forces no reasoning, and asks
for a single short action phrase. If Codex is unavailable, fails, or times out,
the hook uses the local compact summary and still sends the notification.

GitHub PR links in assistant summaries are sent through Pushover's explicit
`url` and `url_title` fields. Markdown link URLs are stripped from the visible
message body before truncation so the client does not auto-link a stale or
partial URL.

## Status Detection

| Setting | Default | Purpose |
| --- | --- | --- |
| `attention_status_terms` | failure/blocking terms | Terms that classify a turn as `Needs attention`. |
| `negated_status_terms` | negation terms | Phrases removed before attention matching, such as `no errors`. |

These terms drive the title status and `notify_on_failure`.

## Focus Suppression

Focus suppression is disabled by default.

| Setting | Default | Purpose |
| --- | --- | --- |
| `focus_policy` | `"always"` | `always` disables focus checks; `when_codex_unfocused` skips when Codex is frontmost. |
| `focus_app_names` | `["Codex"]` | Frontmost app names treated as Codex. |
| `focus_unknown_policy` | `"send"` | On focus-check failure, either `send` or `skip`. |
| `focus_check_timeout_seconds` | `1` | Timeout for the macOS focus check. |

The focus check uses `/usr/bin/osascript` and System Events. macOS may require
Automation or Accessibility permission for the process running Codex hooks.
`[notify]` and sample sends bypass focus suppression.

## Delivery

| Setting | Default | Purpose |
| --- | --- | --- |
| `retry_attempts` | `2` | Pushover publish attempts. |
| `retry_backoff_seconds` | `[1, 2]` | Backoff schedule between failed attempts. |
| `http_timeout_seconds` | `5` | Per-request HTTP timeout. |
| `pushover_priority` | `0` | Pushover priority. |
| `pushover_sound` | `""` | Optional Pushover sound. |
| `pushover_device` | `""` | Optional target device. |

## Notification History

| Setting | Default | Purpose |
| --- | --- | --- |
| `history_enabled` | `true` | Store delivered and dry-run notifications in SQLite for later formatter review. |
| `history_db_path` | `""` | Optional custom notification-history SQLite path. |
| `history_store_messages` | `true` | Store rendered notification title/body. Disable to keep only metadata and length fields. |
| `history_retention_days` | `90` | Delete history rows older than this many days. Use `0` to keep all rows. |

History is stored separately from dedupe state at `notify_history.sqlite3` by
default. It records the rendered Pushover title/body, delivery metadata, policy
decision, duration, repo/branch/short SHA, and link fields. It does not store
Pushover credentials or raw transcript content.

If you want metadata without stored notification bodies, set:

```toml
history_store_messages = false
```

If you do not want local history at all, set:

```toml
history_enabled = false
```

To review the history in a local debug page:

```bash
python3 tools/notification_history_server.py
```

The page serves on `http://127.0.0.1:60605` by default.

## Runtime Paths

| Setting | Default | Purpose |
| --- | --- | --- |
| `pushover_env_path` | `""` | Optional custom `.pushover.env` path. |
| `state_db_path` | `""` | Optional custom SQLite dedupe DB path. |
| `dedupe_enabled` | `true` | Prevent duplicate sends for the same turn id. Disable only for debugging. |

## Environment Overrides

Use environment overrides for one-off smoke tests, local debugging, or temporary
policy changes. Prefer `config.toml` for normal behavior.

| Variable | Purpose |
| --- | --- |
| `CODEX_NOTIFY` | One-run policy override: `always`, `long`, or `none`. |
| `CODEX_NOTIFY_DRY_RUN` | When truthy, records/logs what would be sent without publishing to Pushover. |
| `CODEX_PUSHOVER_SAMPLE` | Set to `1` to send an explicit sample notification. |
| `CODEX_PUSHOVER_CONFIG` | Path to a config file to use instead of the normal lookup order. |
| `CODEX_PUSHOVER_ENV` | Path to a `.pushover.env` file to use before configured/default credential paths. |

Common smoke-test override:

```bash
CODEX_NOTIFY_DRY_RUN=1 CODEX_NOTIFY=always codex exec \
  -c 'notify=[]' \
  --cd "$PWD" \
  "Reply exactly: dry run complete"
```
