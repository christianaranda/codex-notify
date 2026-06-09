from __future__ import annotations

import io
import json
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "codex-notify"
    / "hooks"
    / "codex_notify.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("codex_notify", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CodexNotifyTests(unittest.TestCase):
    def test_normalizes_stop_payload(self):
        module = load_module()
        event = module.normalize_event(
            {
                "hook_event_name": "Stop",
                "session_id": "session",
                "turn_id": "turn",
                "cwd": "/tmp/example",
                "last_assistant_message": "Done.",
                "stop_hook_active": False,
            }
        )
        self.assertEqual(event["source"], "stop")
        self.assertEqual(event["turn_id"], "turn")
        self.assertEqual(event["cwd"], "/tmp/example")

    def test_reads_subagent_metadata_from_transcript_header(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript_path = Path(temp_dir) / "subagent.jsonl"
            transcript_path.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "thread_source": "subagent",
                            "originator": "Codex Desktop",
                            "source": {"subagent": {"other": "guardian"}},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            metadata = module.session_meta_from_transcript(str(transcript_path))
            event = {"transcript_path": str(transcript_path)}
            module.apply_session_metadata(event, metadata)
        self.assertTrue(module.is_subagent_event(event))
        self.assertEqual(event["thread_source"], "subagent")
        self.assertEqual(event["subagent_name"], "guardian")
        self.assertEqual(event["originator"], "Codex Desktop")

    def test_policy_tags_override_default(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(module.choose_policy(config, "please do this [no-notify]"), "none")
            self.assertEqual(module.choose_policy(config, "please do this [notify]"), "always")

    def test_focus_policy_skips_when_codex_is_frontmost(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            focus_policy="when_codex_unfocused",
            focus_app_names=["Codex"],
        )
        original = module.frontmost_app_name
        try:
            module.frontmost_app_name = lambda timeout: "Codex"
            skip, reason, frontmost = module.should_skip_for_focus(config, "")
        finally:
            module.frontmost_app_name = original
        self.assertTrue(skip)
        self.assertEqual(reason, "app_focused")
        self.assertEqual(frontmost, "Codex")

    def test_focus_policy_sends_when_other_app_is_frontmost(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            focus_policy="when_codex_unfocused",
            focus_app_names=["Codex"],
        )
        original = module.frontmost_app_name
        try:
            module.frontmost_app_name = lambda timeout: "Safari"
            skip, reason, frontmost = module.should_skip_for_focus(config, "")
        finally:
            module.frontmost_app_name = original
        self.assertFalse(skip)
        self.assertEqual(reason, "app_unfocused")
        self.assertEqual(frontmost, "Safari")

    def test_focus_policy_send_on_unknown_is_fail_open(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            focus_policy="when_codex_unfocused",
            focus_unknown_policy="send",
        )
        original = module.frontmost_app_name
        try:
            module.frontmost_app_name = lambda timeout: None
            skip, reason, frontmost = module.should_skip_for_focus(config, "")
        finally:
            module.frontmost_app_name = original
        self.assertFalse(skip)
        self.assertEqual(reason, "focus_unknown")
        self.assertIsNone(frontmost)

    def test_focus_policy_explicit_notify_tag_bypasses_focus(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            focus_policy="when_codex_unfocused",
            focus_app_names=["Codex"],
        )
        original = module.frontmost_app_name
        try:
            module.frontmost_app_name = lambda timeout: "Codex"
            skip, reason, frontmost = module.should_skip_for_focus(config, "do it [notify]")
        finally:
            module.frontmost_app_name = original
        self.assertFalse(skip)
        self.assertEqual(reason, "focus_bypassed")
        self.assertIsNone(frontmost)

    def test_notification_uses_scope_and_message(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG)
        title, body = module.build_notification(
            config,
            {
                "cwd": "/tmp/example",
                "last_assistant_message": "Everything completed successfully.",
                "model": "gpt-test",
            },
            61,
        )
        self.assertEqual(title, "Done: example | 1m 1s")
        self.assertIn("1m 1s", body)
        self.assertIn("<b>Status</b>", body)
        self.assertIn("<b>Result</b>", body)
        self.assertIn("Everything completed successfully.", body)

    def test_notification_templates_and_metadata_flags_are_configurable(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            title_template="{scope} finished",
            message_template="{status}\n{outcome}",
            include_duration=False,
            include_host=False,
            include_model=False,
        )
        title, body = module.build_notification(
            config,
            {
                "cwd": "/tmp/example",
                "last_assistant_message": "Everything completed successfully.",
                "model": "gpt-test",
            },
            61,
        )
        self.assertEqual(title, "example finished")
        self.assertEqual(body, "Done\nEverything completed successfully.")
        self.assertNotIn("gpt-test", body)

    def test_notification_extracts_pr_url_without_leaking_markdown_url_to_body(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG)
        message = (
            "Merged: [example-org/example-app#546]"
            "(https://github.com/example-org/example-app/pull/546)\n\n"
            "Post-merge status is green."
        )
        title, body = module.build_notification(
            config,
            {
                "cwd": "/tmp/example",
                "last_assistant_message": message,
                "model": "gpt-test",
            },
            61,
        )
        self.assertEqual(title, "Done: example | 1m 1s")
        self.assertIn("Merged: example-org/example-app#546", body)
        self.assertIn("<b>PR</b>: example-org/example-app#546", body)
        self.assertNotIn("https://github.com", body)
        self.assertEqual(
            module.notification_link_from_message(message),
            (
                "https://github.com/example-org/example-app/pull/546",
                "example-org/example-app#546",
            ),
        )

    def test_notification_strips_markdown_markup_from_result(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG, include_git=False)
        message = (
            "Agreed. We should implement Kernel Managed Auth.\n\n"
            "**What I found**\n"
            "- Start login, send user to `hosted_url`, then launch browsers "
            "with `profile: { name }` and `stealth: true`.\n"
            "### Next step\n"
            "> Replace the old capture flow."
        )
        _title, body = module.build_notification(
            config,
            {
                "cwd": "/tmp/example",
                "last_assistant_message": message,
                "model": "gpt-test",
            },
            61,
        )
        self.assertIn("What I found", body)
        self.assertIn("hosted_url", body)
        self.assertIn("Next step", body)
        self.assertNotIn("**", body)
        self.assertNotIn("`", body)
        self.assertNotIn("###", body)

    def test_notification_extracts_raw_pr_url_from_explicit_pr_line(self):
        module = load_module()
        self.assertEqual(
            module.notification_link_from_message(
                "PR: https://github.com/example-org/example-app/pull/546"
            ),
            (
                "https://github.com/example-org/example-app/pull/546",
                "example-org/example-app#546",
            ),
        )
        self.assertEqual(
            module.notification_link_from_message(
                "Opened non-draft PR #546: Useful notifications\n"
                "https://github.com/example-org/example-app/pull/546"
            ),
            (
                "https://github.com/example-org/example-app/pull/546",
                "example-org/example-app#546",
            ),
        )

    def test_notification_ignores_incidental_pr_url_mentions(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG)
        message = (
            "Verified row 17 in the browser: it now shows `url title` plus "
            "`https://github.com/example-org/example-app/pull/568` as the "
            "raw clickable URL.\n\n"
            "Debug page is still running at http://127.0.0.1:60605."
        )
        self.assertIsNone(module.notification_link_from_message(message))
        _title, body = module.build_notification(
            config,
            {
                "cwd": "/tmp/example",
                "last_assistant_message": message,
                "model": "gpt-test",
            },
            61,
        )
        self.assertNotIn("<b>PR</b>:", body)

    def test_notification_includes_prompt_git_and_verification_details(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG, task_summary_mode="local")
        original_git_context = module.git_context
        try:
            module.git_context = lambda cwd, timeout: {
                "repo": "repo",
                "branch": "feature/push",
                "git_sha": "abc1234",
                "git_dirty": "2 changed",
                "git_changed_count": "2",
                "git_root": "/tmp/repo",
            }
            title, body = module.build_notification(
                config,
                {
                    "cwd": "/tmp/repo",
                    "latest_input": "make the push useful [notify]",
                    "last_assistant_message": (
                        "Implemented richer notifications.\n\n"
                        "Verification: python3 -m unittest discover -s tests"
                    ),
                    "model": "gpt-test",
                },
                120,
            )
        finally:
            module.git_context = original_git_context

        self.assertEqual(title, "Done: repo | feature/push | 2m")
        self.assertIn("<b>Prompt</b>: make the push useful", body)
        self.assertIn("<b>Verified</b>: python3 -m unittest discover -s tests", body)
        self.assertIn("<b>Repo</b>: repo | feature/push | abc1234 | 2 changed", body)
        self.assertIn("<b>Runtime</b>: gpt-test", body)

    def test_truncation_uses_word_boundaries(self):
        module = load_module()
        truncated = module.truncate_text("passes, 24 tests completed", 17)
        self.assertEqual(truncated, "passes, 24...")
        self.assertNotIn("test...", truncated)

    def test_default_details_fit_without_trailing_fragment(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            include_git=False,
            task_summary_mode="local",
            max_message_chars=260,
            max_outcome_chars=900,
            max_task_chars=400,
        )
        message = (
            "Implemented a long notification formatter that says a lot. " * 12
            + "\n\nVerification: python3 -m unittest discover -s tests passes, 24 tests"
        )
        _title, body = module.build_notification(
            config,
            {
                "cwd": "/tmp/example",
                "latest_input": (
                    "please make the push notification useful and avoid cutting off "
                    "the final words "
                )
                * 5,
                "last_assistant_message": message,
                "model": "gpt-test",
            },
            61,
        )
        self.assertLessEqual(len(body), 260)
        self.assertNotIn("24 test...", body)
        self.assertFalse(body.endswith("..."))
        self.assertIn("<b>Repo</b>: example", body)

    def test_local_task_summary_compacts_long_rollout_prompt(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            task_summary_mode="local",
            task_summary_max_chars=96,
        )
        task = module.extract_task(
            (
                "we did a bunch of work in dev, and it's about time we do a prod rollout. "
                "some questions about this though. I think we just tag dev and roll it out, "
                "but I think we have a gap in our production terraform."
            ),
            config,
            220,
        )
        self.assertEqual(task, "find next steps for prod rollout and terraform gaps")
        self.assertNotIn("...", task)

    def test_task_summary_ignores_selected_text_wrapper(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG, task_summary_mode="local")
        task = module.extract_task(
            (
                "# Selected text:\n\n"
                "## Selection 1\n"
                "Default task_summary_mode = \"auto\":Uses OpenAI Responses API "
                "if OPENAI_API_KEY is available.\n\n"
                "## My request for Codex:\n"
                "why can't it just use codex? I don't want to use keys like this\n"
            ),
            config,
            220,
        )
        self.assertEqual(task, "why can't it just use codex")
        self.assertNotIn("Selected text", task)
        self.assertNotIn("OPENAI_API_KEY", task)

    def test_task_summary_uses_last_request_heading_in_selected_text_wrapper(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG, task_summary_mode="local")
        task = module.extract_task(
            (
                "# Selected text:\n\n"
                "## Selection 1\n"
                "## My request for Codex: section before task summarization.\n\n"
                "## My request for Codex:\n"
                "it should either say task or my request or better yet change it "
                "to say only prompt then the modified prompt\n"
            ),
            config,
            220,
        )
        self.assertIn("only prompt", task)
        self.assertNotIn("section before task summarization", task)

    def test_latest_user_input_skips_injected_skill_blocks(self):
        module = load_module()
        items = [
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "we only apply terraform from merged PR. "
                                "make sure the plan has no local changes. "
                                "[$terraform-dev-wrapper]"
                                "(/Users/example/.codex/skills/terraform-dev-wrapper/SKILL.md)"
                            ),
                        }
                    ],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "<skill>\n"
                                "<name>terraform-dev-wrapper</name>\n"
                                "<path>/Users/example/.codex/skills/terraform-dev-wrapper/SKILL.md</path>\n"
                                "Use for Terraform work.\n"
                            ),
                        }
                    ],
                },
            },
        ]

        latest = module.latest_user_input_from_transcript(items)

        self.assertIn("we only apply terraform", latest)
        self.assertIn("terraform-dev-wrapper", latest)
        self.assertNotIn("[$terraform", latest)
        self.assertNotIn("/Users/example", latest)
        self.assertNotIn("<skill>", latest)

    def test_task_summary_strips_skill_tags_and_paths(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG, task_summary_mode="local")
        task = module.extract_task(
            (
                "we only apply terraform from merged PR. "
                "make sure it does not use local changes. "
                "[$terraform-dev-wrapper]"
                "(/Users/example/.codex/skills/terraform-dev-wrapper/SKILL.md)\n\n"
                "<skill><name>terraform-dev-wrapper</name>"
                "<path>/Users/example/.codex/skills/terraform-dev-wrapper/SKILL.md</path>"
                "Use for Terraform work.</skill>"
            ),
            config,
            220,
        )

        self.assertIn("we only apply terraform", task)
        self.assertNotIn("[$terraform", task)
        self.assertNotIn("/Users/example", task)
        self.assertNotIn("<skill", task)

    def test_notification_uses_task_summary_without_generated_ellipsis(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            include_git=False,
            task_summary_mode="local",
            max_message_chars=500,
            max_outcome_chars=260,
        )
        _title, body = module.build_notification(
            config,
            {
                "cwd": "/tmp/example",
                "latest_input": (
                    "we did a bunch of work in dev, and it's about time we do a prod rollout. "
                    "some questions about this though. I think we just tag dev and roll it out, "
                    "but I think we have a gap in our production terraform."
                ),
                "last_assistant_message": (
                    "Reviewed production rollout and Terraform gaps. "
                    "Identified platform-only tag automation and manual app Terraform applies."
                ),
                "model": "gpt-test",
            },
            621,
        )
        self.assertIn(
            "<b>Prompt</b>: find next steps for prod rollout and terraform gaps",
            body,
        )
        self.assertNotIn("under...", body)
        self.assertNotIn("...", body)

    def test_codex_task_summary_uses_codex_exec_when_available(self):
        module = load_module()
        captured = {}

        class FakeCompleted:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(args, input, text, capture_output, timeout, check):
            captured["args"] = args
            captured["input"] = input
            captured["timeout"] = timeout
            output_path = Path(args[args.index("-o") + 1])
            output_path.write_text("find prod rollout terraform gaps.\n", encoding="utf-8")
            return FakeCompleted()

        config = dict(
            module.DEFAULT_CONFIG,
            task_summary_mode="codex",
            task_summary_codex_model="gpt-5-mini",
            task_summary_timeout_seconds=1.5,
        )
        original_run = module.subprocess.run
        original_which = module.shutil.which
        try:
            module.subprocess.run = fake_run
            module.shutil.which = lambda command: "/usr/local/bin/codex" if command == "codex" else None
            task = module.extract_task("Please investigate rollout next steps.", config, 220)
        finally:
            module.subprocess.run = original_run
            module.shutil.which = original_which

        self.assertEqual(task, "find prod rollout terraform gaps")
        self.assertEqual(captured["args"][0], "/usr/local/bin/codex")
        self.assertIn("exec", captured["args"])
        self.assertIn("--ephemeral", captured["args"])
        self.assertIn("--ignore-rules", captured["args"])
        self.assertIn("--ignore-user-config", captured["args"])
        self.assertIn("hooks", captured["args"])
        self.assertIn('model_reasoning_effort="none"', captured["args"])
        self.assertIn("-a", captured["args"])
        self.assertIn("never", captured["args"])
        self.assertIn("gpt-5-mini", captured["args"])
        exec_index = captured["args"].index("exec")
        self.assertLess(captured["args"].index("-a"), exec_index)
        self.assertLess(captured["args"].index("--sandbox"), exec_index)
        self.assertGreater(captured["args"].index("--ignore-user-config"), exec_index)
        self.assertIn("User task:", captured["input"])
        self.assertEqual(captured["timeout"], 1.5)

    def test_status_ignores_negated_error_language(self):
        module = load_module()
        self.assertEqual(module.classify_status("Completed with no errors."), "Done")
        self.assertEqual(module.classify_status("Completed without failures."), "Done")
        self.assertEqual(module.classify_status("Avoid revealing failure modes."), "Done")
        self.assertEqual(module.classify_status("Tests failed."), "Needs attention")

    def test_status_terms_are_configurable(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            attention_status_terms=["manual review"],
            negated_status_terms=["no manual review"],
        )
        self.assertEqual(module.classify_status("Needs manual review.", config), "Needs attention")
        self.assertEqual(module.classify_status("Needs no manual review.", config), "Done")
        self.assertEqual(module.classify_status("Tests failed.", config), "Done")

    def test_long_policy_notifies_on_failure_when_enabled(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG, default_policy="long", notify_on_failure=True)
        send, reason = module.should_send(config, "long", 5, "Needs attention")
        self.assertTrue(send)
        self.assertEqual(reason, "attention_status")

    def test_long_policy_leaves_short_failures_quiet_by_default(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG, default_policy="long")
        send, reason = module.should_send(config, "long", 5, "Needs attention")
        self.assertFalse(send)
        self.assertEqual(reason, "duration_below_threshold")
        send, reason = module.should_send({}, "long", 5, "Needs attention")
        self.assertFalse(send)
        self.assertEqual(reason, "duration_below_threshold")

    def test_long_policy_can_leave_short_failures_quiet(self):
        module = load_module()
        config = dict(module.DEFAULT_CONFIG, default_policy="long", notify_on_failure=False)
        send, reason = module.should_send(config, "long", 5, "Needs attention")
        self.assertFalse(send)
        self.assertEqual(reason, "duration_below_threshold")

    def test_stop_hook_active_is_not_a_send_event(self):
        module = load_module()
        event = module.normalize_event(
            {
                "hook_event_name": "Stop",
                "turn_id": "turn",
                "stop_hook_active": True,
            }
        )
        self.assertIs(event["stop_hook_active"], True)

    def test_load_simple_env_accepts_export_and_quotes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".pushover.env"
            env_path.write_text(
                "export PUSHOVER_USER_KEY='user-key'\n"
                'PUSHOVER_APP_TOKEN="app-token"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                module.load_simple_env(env_path),
                {
                    "PUSHOVER_USER_KEY": "user-key",
                    "PUSHOVER_APP_TOKEN": "app-token",
                },
            )

    def test_load_config_supports_env_overrides(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.toml"
            env_path = root / "credentials.env"
            config_path.write_text('default_policy = "long"\n', encoding="utf-8")
            env_path.write_text(
                "PUSHOVER_USER_KEY=user-key\nPUSHOVER_APP_TOKEN=app-token\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_PUSHOVER_CONFIG": str(config_path),
                    "CODEX_PUSHOVER_ENV": str(env_path),
                },
                clear=True,
            ):
                config = module.load_config()
            self.assertEqual(config["default_policy"], "long")
            self.assertEqual(config["PUSHOVER_USER_KEY"], "user-key")
            self.assertEqual(config["PUSHOVER_APP_TOKEN"], "app-token")
            self.assertEqual(config["loaded_config_path"], str(config_path))
            self.assertEqual(config["loaded_pushover_env_path"], str(env_path))

    def test_acquire_turn_lock_deduplicates(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "state.sqlite3"
            self.assertTrue(module.acquire_turn_lock(db_path, "turn-1"))
            self.assertFalse(module.acquire_turn_lock(db_path, "turn-1"))
            self.assertTrue(module.acquire_turn_lock(db_path, "turn-2"))

    def test_records_notification_history(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            config = dict(module.DEFAULT_CONFIG, history_db_path=str(db_path), include_git=False)
            history_id = module.record_notification_history(
                config,
                {
                    "turn_id": "turn",
                    "session_id": "session",
                    "cwd": "/tmp/example",
                    "model": "gpt-test",
                    "permission_mode": "on-request",
                    "thread_source": "user",
                },
                title="Done: example",
                message="<b>Status</b>: Done\n<b>Result</b>: Finished.",
                request_id="req-123",
                url="https://github.com/example/repo/pull/1",
                url_title="example/repo#1",
                policy="long",
                reason="duration_threshold_met",
                status="Done",
                sample=False,
                focus_reason="focus_policy_always",
                frontmost_app=None,
                duration_seconds=301.2,
            )

            self.assertEqual(history_id, 1)
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT title, message, request_id, url_title, message_chars,
                           policy, reason, duration_seconds, model
                    FROM notification_history
                    """
                ).fetchone()
            finally:
                conn.close()

        self.assertEqual(row[0], "Done: example")
        self.assertIn("<b>Result</b>: Finished.", row[1])
        self.assertEqual(row[2], "req-123")
        self.assertEqual(row[3], "example/repo#1")
        self.assertEqual(row[4], len("<b>Status</b>: Done\n<b>Result</b>: Finished."))
        self.assertEqual(row[5], "long")
        self.assertEqual(row[6], "duration_threshold_met")
        self.assertEqual(row[7], 301.2)
        self.assertEqual(row[8], "gpt-test")

    def test_notification_history_migrates_older_schema(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE notification_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at INTEGER NOT NULL,
                        turn_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            config = dict(module.DEFAULT_CONFIG, history_db_path=str(db_path), include_git=False)
            history_id = module.record_notification_history(
                config,
                {
                    "turn_id": "turn",
                    "session_id": "session",
                    "cwd": "/tmp/example",
                    "model": "gpt-test",
                },
                title="Done: example",
                message="<b>Status</b>: Done",
                request_id="req-123",
                url="",
                url_title="",
                policy="always",
                reason="policy_always",
                status="Done",
                sample=False,
                focus_reason="focus_policy_always",
                frontmost_app=None,
                duration_seconds=1.0,
            )

            self.assertEqual(history_id, 1)
            conn = sqlite3.connect(db_path)
            try:
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(notification_history)")
                }
                row = conn.execute(
                    "SELECT session_id, request_id, message_html, model FROM notification_history"
                ).fetchone()
            finally:
                conn.close()

        self.assertIn("session_id", columns)
        self.assertIn("payload_json", columns)
        self.assertEqual(row, ("session", "req-123", 1, "gpt-test"))

    def test_publish_pushover_builds_expected_request(self):
        module = load_module()
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"status": 1, "request": "req-123"}'

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["data"] = req.data
            captured["timeout"] = timeout
            return FakeResponse()

        config = dict(
            module.DEFAULT_CONFIG,
            PUSHOVER_USER_KEY="user-key",
            PUSHOVER_APP_TOKEN="app-token",
            PUSHOVER_SOUND="magic",
            PUSHOVER_DEVICE="phone",
            retry_attempts=1,
            http_timeout_seconds=3,
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            original_urlopen = module.request.urlopen
            try:
                module.request.urlopen = fake_urlopen
                request_id = module.publish_pushover(
                    config,
                    "Title",
                    "Body",
                    url="https://github.com/example-org/example-app/pull/546",
                    url_title="example-org/example-app#546",
                )
            finally:
                module.request.urlopen = original_urlopen

        self.assertEqual(request_id, "req-123")
        self.assertEqual(captured["url"], "https://api.pushover.net/1/messages.json")
        self.assertEqual(captured["timeout"], 3)
        body = module.parse.parse_qs(captured["data"].decode("utf-8"))
        self.assertEqual(body["token"], ["app-token"])
        self.assertEqual(body["user"], ["user-key"])
        self.assertEqual(body["html"], ["1"])
        self.assertEqual(body["sound"], ["magic"])
        self.assertEqual(body["device"], ["phone"])
        self.assertEqual(
            body["url"],
            ["https://github.com/example-org/example-app/pull/546"],
        )
        self.assertEqual(body["url_title"], ["example-org/example-app#546"])

    def test_custom_html_template_truncation_does_not_leave_partial_tag(self):
        module = load_module()
        config = dict(
            module.DEFAULT_CONFIG,
            include_git=False,
            max_message_chars=100,
            message_template=("A" * 70) + " {details}",
        )
        _title, body = module.build_notification(
            config,
            {
                "cwd": "/tmp/example",
                "last_assistant_message": "Done.",
                "model": "gpt-test",
            },
            61,
        )
        self.assertLessEqual(len(body), 100)
        self.assertNotRegex(body, r"<[^>]*$")
        self.assertNotIn("<font", body)

    def test_publish_failure_releases_turn_lock(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_values = {
                "PLUGIN_DATA": module.PLUGIN_DATA,
                "USER_DATA": module.USER_DATA,
                "LOG_PATH": module.LOG_PATH,
                "DEFAULT_CONFIG_PATH": module.DEFAULT_CONFIG_PATH,
                "DEFAULT_ENV_PATH": module.DEFAULT_ENV_PATH,
                "DEFAULT_STATE_DB_PATH": module.DEFAULT_STATE_DB_PATH,
                "DEFAULT_HISTORY_DB_PATH": module.DEFAULT_HISTORY_DB_PATH,
            }
            old_publish = module.publish_pushover
            module.PLUGIN_DATA = root
            module.USER_DATA = root / "user"
            module.LOG_PATH = root / "notify.log"
            module.DEFAULT_CONFIG_PATH = root / "missing-config.toml"
            module.DEFAULT_ENV_PATH = root / "missing-env"
            module.DEFAULT_STATE_DB_PATH = root / "state.sqlite3"
            module.DEFAULT_HISTORY_DB_PATH = root / "history.sqlite3"
            payload = {
                "hook_event_name": "Stop",
                "session_id": "session",
                "turn_id": "turn",
                "cwd": str(root),
                "last_assistant_message": "Done.",
            }
            calls = []

            def fake_publish(*args, **kwargs):
                calls.append(kwargs)
                if len(calls) == 1:
                    raise RuntimeError("publish failed")
                return "req-123"

            module.publish_pushover = fake_publish
            try:
                with mock.patch.dict(os.environ, {"CODEX_NOTIFY": "always"}, clear=True):
                    with self.assertRaises(RuntimeError):
                        module.process_payload(payload)
                    module.process_payload(payload)

                conn = sqlite3.connect(module.DEFAULT_STATE_DB_PATH)
                try:
                    lock_count = conn.execute("SELECT COUNT(*) FROM processed_turns").fetchone()[0]
                finally:
                    conn.close()
                self.assertEqual(lock_count, 1)
                self.assertTrue(module.DEFAULT_HISTORY_DB_PATH.exists())
                self.assertEqual(len(calls), 2)
            finally:
                module.publish_pushover = old_publish
                for key, value in old_values.items():
                    setattr(module, key, value)

    def test_process_payload_collects_git_context_once(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_values = {
                "PLUGIN_DATA": module.PLUGIN_DATA,
                "USER_DATA": module.USER_DATA,
                "LOG_PATH": module.LOG_PATH,
                "DEFAULT_CONFIG_PATH": module.DEFAULT_CONFIG_PATH,
                "DEFAULT_ENV_PATH": module.DEFAULT_ENV_PATH,
                "DEFAULT_STATE_DB_PATH": module.DEFAULT_STATE_DB_PATH,
                "DEFAULT_HISTORY_DB_PATH": module.DEFAULT_HISTORY_DB_PATH,
            }
            old_git_context = module.git_context
            module.PLUGIN_DATA = root
            module.USER_DATA = root / "user"
            module.LOG_PATH = root / "notify.log"
            module.DEFAULT_CONFIG_PATH = root / "missing-config.toml"
            module.DEFAULT_ENV_PATH = root / "missing-env"
            module.DEFAULT_STATE_DB_PATH = root / "state.sqlite3"
            module.DEFAULT_HISTORY_DB_PATH = root / "history.sqlite3"
            calls = []

            def fake_git_context(cwd, timeout):
                calls.append((cwd, timeout))
                return {
                    "repo": "repo",
                    "branch": "main",
                    "git_sha": "abc1234",
                    "git_dirty": "clean",
                    "git_changed_count": "0",
                    "git_root": str(root),
                }

            module.git_context = fake_git_context
            payload = {
                "hook_event_name": "Stop",
                "session_id": "session",
                "turn_id": "turn",
                "cwd": str(root),
                "last_assistant_message": "Done.",
            }
            try:
                with mock.patch.dict(
                    os.environ,
                    {"CODEX_NOTIFY": "always", "CODEX_NOTIFY_DRY_RUN": "1"},
                    clear=True,
                ):
                    module.process_payload(payload)
                self.assertEqual(len(calls), 1)
            finally:
                module.git_context = old_git_context
                for key, value in old_values.items():
                    setattr(module, key, value)

    def test_hook_manifest_timeout_covers_default_budget(self):
        hooks_path = MODULE_PATH.parent / "hooks.json"
        payload = json.loads(hooks_path.read_text(encoding="utf-8"))
        timeout = payload["hooks"]["Stop"][0]["hooks"][0]["timeout"]
        self.assertGreaterEqual(timeout, 30)

    def test_process_payload_does_not_lock_skipped_turns(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_values = {
                "PLUGIN_DATA": module.PLUGIN_DATA,
                "USER_DATA": module.USER_DATA,
                "LOG_PATH": module.LOG_PATH,
                "DEFAULT_CONFIG_PATH": module.DEFAULT_CONFIG_PATH,
                "DEFAULT_ENV_PATH": module.DEFAULT_ENV_PATH,
                "DEFAULT_STATE_DB_PATH": module.DEFAULT_STATE_DB_PATH,
                "DEFAULT_HISTORY_DB_PATH": module.DEFAULT_HISTORY_DB_PATH,
            }
            module.PLUGIN_DATA = root
            module.USER_DATA = root / "user"
            module.LOG_PATH = root / "notify.log"
            module.DEFAULT_CONFIG_PATH = root / "missing-config.toml"
            module.DEFAULT_ENV_PATH = root / "missing-env"
            module.DEFAULT_STATE_DB_PATH = root / "state.sqlite3"
            module.DEFAULT_HISTORY_DB_PATH = root / "history.sqlite3"
            payload = {
                "hook_event_name": "Stop",
                "session_id": "session",
                "turn_id": "turn",
                "cwd": str(root),
                "last_assistant_message": "Done.",
            }
            try:
                with mock.patch.dict(
                    os.environ,
                    {"CODEX_NOTIFY": "long", "CODEX_NOTIFY_DRY_RUN": "1"},
                    clear=True,
                ):
                    module.process_payload(payload)
                self.assertFalse(module.DEFAULT_STATE_DB_PATH.exists())

                with mock.patch.dict(
                    os.environ,
                    {"CODEX_NOTIFY": "always", "CODEX_NOTIFY_DRY_RUN": "1"},
                    clear=True,
                ):
                    module.process_payload(payload)
                self.assertTrue(module.DEFAULT_STATE_DB_PATH.exists())
                self.assertTrue(module.DEFAULT_HISTORY_DB_PATH.exists())
                log_text = module.LOG_PATH.read_text(encoding="utf-8")
                self.assertIn('"event": "sent"', log_text)
                self.assertIn('"history_id": 1', log_text)
            finally:
                for key, value in old_values.items():
                    setattr(module, key, value)

    def test_process_payload_skips_subagents_by_default(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript_path = root / "subagent.jsonl"
            transcript_path.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "thread_source": "subagent",
                            "source": {"subagent": {"other": "guardian"}},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            old_values = {
                "PLUGIN_DATA": module.PLUGIN_DATA,
                "USER_DATA": module.USER_DATA,
                "LOG_PATH": module.LOG_PATH,
                "DEFAULT_CONFIG_PATH": module.DEFAULT_CONFIG_PATH,
                "DEFAULT_ENV_PATH": module.DEFAULT_ENV_PATH,
                "DEFAULT_STATE_DB_PATH": module.DEFAULT_STATE_DB_PATH,
                "DEFAULT_HISTORY_DB_PATH": module.DEFAULT_HISTORY_DB_PATH,
            }
            module.PLUGIN_DATA = root
            module.USER_DATA = root / "user"
            module.LOG_PATH = root / "notify.log"
            module.DEFAULT_CONFIG_PATH = root / "missing-config.toml"
            module.DEFAULT_ENV_PATH = root / "missing-env"
            module.DEFAULT_STATE_DB_PATH = root / "state.sqlite3"
            module.DEFAULT_HISTORY_DB_PATH = root / "history.sqlite3"
            payload = {
                "hook_event_name": "Stop",
                "session_id": "session",
                "turn_id": "turn",
                "transcript_path": str(transcript_path),
                "cwd": str(root),
                "last_assistant_message": "Done.",
            }
            try:
                with mock.patch.dict(
                    os.environ,
                    {"CODEX_NOTIFY": "always", "CODEX_NOTIFY_DRY_RUN": "1"},
                    clear=True,
                ):
                    module.process_payload(payload)
                self.assertFalse(module.DEFAULT_STATE_DB_PATH.exists())
                records = [
                    json.loads(line)
                    for line in module.LOG_PATH.read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(records[-1]["event"], "skipped")
                self.assertEqual(records[-1]["reason"], "subagent")
                self.assertEqual(records[-1]["subagent_name"], "guardian")
            finally:
                for key, value in old_values.items():
                    setattr(module, key, value)

    def test_process_payload_can_notify_subagents_when_enabled(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript_path = root / "subagent.jsonl"
            transcript_path.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "thread_source": "subagent",
                            "source": {"subagent": {"other": "guardian"}},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config_path = root / "config.toml"
            config_path.write_text("notify_subagents = true\n", encoding="utf-8")
            old_values = {
                "PLUGIN_DATA": module.PLUGIN_DATA,
                "USER_DATA": module.USER_DATA,
                "LOG_PATH": module.LOG_PATH,
                "DEFAULT_CONFIG_PATH": module.DEFAULT_CONFIG_PATH,
                "DEFAULT_ENV_PATH": module.DEFAULT_ENV_PATH,
                "DEFAULT_STATE_DB_PATH": module.DEFAULT_STATE_DB_PATH,
                "DEFAULT_HISTORY_DB_PATH": module.DEFAULT_HISTORY_DB_PATH,
            }
            module.PLUGIN_DATA = root
            module.USER_DATA = root / "user"
            module.LOG_PATH = root / "notify.log"
            module.DEFAULT_CONFIG_PATH = config_path
            module.DEFAULT_ENV_PATH = root / "missing-env"
            module.DEFAULT_STATE_DB_PATH = root / "state.sqlite3"
            module.DEFAULT_HISTORY_DB_PATH = root / "history.sqlite3"
            payload = {
                "hook_event_name": "Stop",
                "session_id": "session",
                "turn_id": "turn",
                "transcript_path": str(transcript_path),
                "cwd": str(root),
                "last_assistant_message": "Done.",
            }
            try:
                with mock.patch.dict(
                    os.environ,
                    {"CODEX_NOTIFY": "always", "CODEX_NOTIFY_DRY_RUN": "1"},
                    clear=True,
                ):
                    module.process_payload(payload)
                self.assertTrue(module.DEFAULT_STATE_DB_PATH.exists())
                self.assertTrue(module.DEFAULT_HISTORY_DB_PATH.exists())
                records = [
                    json.loads(line)
                    for line in module.LOG_PATH.read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(records[-1]["event"], "sent")
                self.assertEqual(records[-1]["thread_source"], "subagent")
                self.assertEqual(records[-1]["subagent_name"], "guardian")
            finally:
                for key, value in old_values.items():
                    setattr(module, key, value)

    def test_main_is_fail_open(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_process_payload = module.process_payload
            old_plugin_data = module.PLUGIN_DATA
            old_log_path = module.LOG_PATH

            def raise_error(payload):
                raise RuntimeError("boom")

            module.process_payload = raise_error
            module.PLUGIN_DATA = root
            module.LOG_PATH = root / "notify.log"
            try:
                with mock.patch("sys.stdin", io.StringIO("{}")):
                    self.assertEqual(module.main(), 0)
                records = [
                    json.loads(line)
                    for line in module.LOG_PATH.read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(records[-1]["event"], "error")
                self.assertIn("boom", records[-1]["error"])
            finally:
                module.process_payload = old_process_payload
                module.PLUGIN_DATA = old_plugin_data
                module.LOG_PATH = old_log_path


if __name__ == "__main__":
    unittest.main()
