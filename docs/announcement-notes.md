# Announcement Notes

Use this when announcing `1.0.0-rc.1` on X, LinkedIn, or in a GitHub release.

## Accurate Positioning

This is a community Codex plugin distributed through a GitHub/repo marketplace.
It is a release candidate, not an OpenAI-curated public Plugin Directory
listing.

Good wording:

```text
I built Codex Notify, a community Codex plugin that sends useful notifications
when Codex turns finish, so you can tell from the notification whether to jump
back in now or leave the result for later. It includes prompt/result summaries,
verification signals, repo metadata, PR links, and local SQLite history for
improving notification quality. The first release candidate ships with Pushover
delivery.
```

Avoid wording that implies:

- Official OpenAI distribution.
- An OpenAI-curated plugin listing.
- Production/stable maturity for every Codex surface.
- Zero setup for all users.

## X Draft

```text
I built Codex Notify, a community Codex plugin that sends richer notifications
when Codex turns finish.

The point is simple: the notification should tell you whether to jump back into
Codex now, open a PR, or let the result sit.

It includes prompt/result summaries, verification signals, repo metadata, PR
links, and local SQLite history so the messages can keep getting better.

RC1 ships with Pushover delivery.

RC1 is out for testing:
<repo URL>
```

## LinkedIn Draft

```text
I have been using Codex for longer-running coding work and wanted notifications
that were more useful than "the task finished."

So I built Codex Notify, a community Codex plugin that sends notifications when
Codex turns finish. The notification includes status, prompt/result summaries,
verification signals, repository metadata, and PR links when Codex reports them.
It also keeps a lightweight local SQLite history so notification quality can be
reviewed and improved over time.

The goal is to make the notification useful enough that you can decide whether
to jump back into Codex, open the PR, or leave the result for later. The first
release candidate ships with Pushover delivery.

The first release candidate is available for testing through a GitHub/repo
marketplace install. It is not an OpenAI-curated plugin; it is a community
plugin for people who use Codex and want richer turn-completion notifications.

Feedback on install friction and message quality is especially useful:
<repo URL>
```

## Pre-Announcement Checks

- Replace `<repo URL>` with the public repository URL.
- Confirm the clean install smoke test passed from the public repo.
- Confirm the README says `1.0.0-rc.1`.
- Confirm no credentials, local logs, or SQLite files are tracked.
- Attach a screenshot or short GIF that does not reveal private prompt,
  repository, branch, path, or Pushover data.
