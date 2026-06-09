# Release Checklist

Use this before publishing a GitHub release, tagging a release candidate, or
announcing the plugin publicly.

## Package Shape

- `plugins/codex-notify/.codex-plugin/plugin.json` has the intended
  version, display name, license, and hook path.
- `plugins/codex-notify/hooks/hooks.json` invokes the hook through
  `PLUGIN_ROOT` and has a timeout that covers the default delivery budget.
- `plugins/codex-notify/tools/setup_pushover_credentials.py` is included and
  creates the credential env file without printing secret values.
- `.agents/plugins/marketplace.json` points at `./plugins/codex-notify`
  for repo-marketplace installs.
- No secrets, local logs, SQLite files, or backup files are tracked.
- The old direct-notify implementation remains outside the public tree.

## Local Validation

```bash
python3 -c 'import json; [json.load(open(p)) for p in [
  ".agents/plugins/marketplace.json",
  "plugins/codex-notify/.codex-plugin/plugin.json",
  "plugins/codex-notify/hooks/hooks.json"
]]'
python3 -m py_compile \
  plugins/codex-notify/hooks/codex_notify.py \
  plugins/codex-notify/tools/setup_pushover_credentials.py \
  tools/notification_history_server.py \
  tests/test_setup_pushover_credentials.py \
  tests/test_notification_history_server.py
python3 -m unittest discover -s tests
```

Run a local artifact/secret check:

```bash
find . -path ./.git -prune -o \
  \( -name '*.sqlite3' -o -name '.pushover.env' -o -name 'notify.log' \) \
  -print

grep -RInE \
  '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|cr-[A-Za-z0-9]{20,}|PUSHOVER_(USER_KEY|APP_TOKEN)=.{10,})' \
  -- README.md docs plugins tests .github .agents
```

Both commands should produce no real findings. Placeholders such as
`PUSHOVER_APP_TOKEN=` are expected.

## Clean Install Smoke Test

1. Use a clean or throwaway Codex home.
2. Add the repo marketplace:

```bash
codex plugin marketplace add christianaranda/codex-notify
```

3. Install `Codex Notify` through the Codex plugin directory.
4. Restart Codex.
5. If Codex reports that hooks need review, run `/hooks`, inspect the
   plugin-bundled command, and trust it if it matches this repo.
6. Confirm hooks are not disabled by user/project/workspace config:

```toml
[features]
hooks = true
```

7. Run a dry-run turn with top-level notify disabled:

```bash
CODEX_NOTIFY_DRY_RUN=1 CODEX_NOTIFY=always codex exec \
  -c 'notify=[]' \
  --cd "$PWD" \
  "Reply exactly: plugin dry run complete"
```

8. Confirm `notify.log` contains `dry_run_publish` and `sent`.
9. Ask Codex to set up real Pushover credentials:

```text
Use Codex Notify to set up Pushover credentials on this Mac. Locate and run the bundled setup_pushover_credentials.py helper. Ask me to type the Pushover user key and app token into the terminal; do not ask me to paste secrets into chat.
```

10. Confirm `~/.codex/codex-notify/.pushover.env` exists without printing its
    values, then send one explicit sample:

```bash
CODEX_PUSHOVER_SAMPLE=1 codex exec \
  -c 'notify=[]' \
  --cd "$PWD" \
  "Reply exactly: plugin sample complete"
```

11. Confirm the sample notification, `notify.log`, and
    `notify_history.sqlite3` all reflect the sample.

## Public Docs Gate

- README explains why the plugin exists, what users get, and the expected
  successful onboarding outcome before it dives into reference details.
- README install instructions match current Codex hook behavior.
- README clearly says this is a community GitHub/repo-marketplace plugin, not an
  OpenAI-curated Plugin Directory listing.
- `docs/configuration.md` starts with common recipes before the full option
  reference.
- `docs/privacy.md` explains Pushover data sharing and local SQLite/log files.
- `docs/announcement-notes.md` has accurate public launch wording and a checked
  screenshot/GIF redaction reminder.
- `docs/configuration.md` matches `config.example.toml` and hook defaults.
- `CHANGELOG.md` includes the release candidate and any config/state changes.
- Issue templates ask for Codex version, OS, install path, config, and redacted
  `notify.log` excerpts.
- `SECURITY.md` explains how to report sensitive issues.

## Release Gate

- Dry run works from the installed plugin cache, not the repo source path.
- Live sample sends after credentials are configured.
- Hook failures exit open and write diagnostics to `notify.log`.
- CI is green.
- Version is bumped.
- Tag is created only after the clean install smoke test passes.
