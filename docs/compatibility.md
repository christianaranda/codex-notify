# Compatibility

Use this page to decide whether the current release candidate matches your
setup before you install it.

## Release Candidate

Version: `1.0.0-rc.1`

Tested onboarding path:

- Codex app/CLI with plugin and hook support.
- macOS.
- Python 3.11+.
- Pushover account with a user key and application token.
- GitHub/repo-marketplace install using `codex plugin marketplace add`.

Current Codex documentation says hooks are enabled by default and uses `hooks`
as the canonical feature key. If hooks are disabled by user, project, or
workspace configuration, set:

```toml
[features]
hooks = true
```

Codex may require review/trust for plugin-bundled hooks. Use `/hooks` if Codex
reports that hooks need review.

## Not Yet Fully Verified

- Other desktop operating systems.
- IDE extension install/use flow.
- Multi-user workspace sharing.
- OpenAI-curated Plugin Directory distribution.

The plugin is currently intended for GitHub/repo-marketplace distribution.
