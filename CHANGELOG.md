# Changelog

All notable user-facing changes will be documented here.

## 1.0.0-rc.1 - 2026-06-08

Release candidate for public GitHub/repo-marketplace distribution.

### Added

- Codex plugin package with `.codex-plugin/plugin.json`, bundled `Stop` hook,
  and repo-local marketplace entry.
- Pushover delivery provider for completed Codex turns.
- Structured notification content: status, prompt summary, result summary,
  verification lines, repo/branch/SHA/dirty state, model, host, duration, and
  explicit PR link fields.
- Local configuration under `PLUGIN_DATA` with fallback to
  `~/.codex/codex-notify/`.
- Local `.pushover.env` credential loading.
- SQLite duplicate suppression in `notify_state.sqlite3`.
- SQLite notification history in `notify_history.sqlite3`.
- Local history debug page at `http://127.0.0.1:60605`.
- Subagent notification opt-in with `notify_subagents`.
- Long-run policy, prompt tags, and cwd include/exclude filters.
- macOS focus suppression option.
- Optional local or Codex-backed prompt summarization.
- Public documentation for install, configuration, troubleshooting, privacy,
  release checks, security reporting, and issue reports.
- Bundled Pushover credential setup helper that prompts locally and creates the
  `.pushover.env` file for users.

### Changed

- Public documentation now leads with why Codex Notify exists, what users get,
  and a clean onboarding path before reference details.
- Quick start now asks Codex to run the credential setup helper instead of
  asking users to hand-author a hidden env file.
- Agent instructions now spell out how Codex should run credential setup
  without collecting secrets in chat.
- Default task summary mode is local and does not require API keys.
- Notification body formatting strips Markdown that Pushover does not render.
- GitHub PR URLs are sent through Pushover's explicit `url` and `url_title`
  fields instead of being left in the message body.
- Hook timeout is 30 seconds to cover bounded retry behavior.

### Fixed

- Dedupe locks are released when Pushover publishing fails, so transient
  delivery failures do not permanently suppress a turn.
- Old notification-history schemas are migrated before insert.
- The local history debug page tolerates missing columns in older SQLite files.
- Git metadata is collected once per sent notification instead of being queried
  separately for formatting and history.
- Custom HTML templates are truncated without leaving dangling partial tags.

### Notes

- This is a release candidate, not a final stable release.
- This is a community plugin distributed through a GitHub/repo marketplace. It
  is not an OpenAI-curated Plugin Directory listing.
- Pushover delivery sends notification content to Pushover. See
  `docs/privacy.md`.
