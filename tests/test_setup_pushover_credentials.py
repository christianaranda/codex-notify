from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "codex-notify"
    / "tools"
    / "setup_pushover_credentials.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("setup_pushover_credentials", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SetupPushoverCredentialsTests(unittest.TestCase):
    def test_render_env_file_validates_required_values(self):
        module = load_module()
        self.assertEqual(
            module.render_env_file("user-key", "app-token"),
            "PUSHOVER_USER_KEY=user-key\nPUSHOVER_APP_TOKEN=app-token\n",
        )
        with self.assertRaises(ValueError):
            module.render_env_file("", "app-token")
        with self.assertRaises(ValueError):
            module.render_env_file("user-key", "bad\ntoken")

    def test_write_env_file_uses_restrictive_permissions(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / ".pushover.env"
            module.write_env_file(path, "user-key", "app-token", force=False)

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "PUSHOVER_USER_KEY=user-key\nPUSHOVER_APP_TOKEN=app-token\n",
            )
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600)

    def test_write_env_file_refuses_existing_file_without_force(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".pushover.env"
            path.write_text("existing\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                module.write_env_file(path, "user-key", "app-token", force=False)

            self.assertEqual(path.read_text(encoding="utf-8"), "existing\n")
            module.write_env_file(path, "user-key", "app-token", force=True)
            self.assertIn("PUSHOVER_APP_TOKEN=app-token", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
