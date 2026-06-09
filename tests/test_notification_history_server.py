from __future__ import annotations

import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "notification_history_server.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("notification_history_server", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NotificationHistoryServerTests(unittest.TestCase):
    def test_notifications_payload_hydrates_missing_old_schema_columns(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
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
                conn.execute(
                    """
                    INSERT INTO notification_history (created_at, turn_id, title, message)
                    VALUES (1, 'turn', 'Done: repo', 'Finished')
                    """
                )
                conn.commit()

                summary = module.summary_payload(conn, db_path)
                payload, status = module.notifications_payload(
                    conn,
                    db_path,
                    {"sort": ["url_title"], "search": ["repo"]},
                )
            finally:
                conn.close()

        self.assertEqual(summary["rows"], 1)
        self.assertEqual(summary["statuses"], [])
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["rows"][0]["title"], "Done: repo")
        self.assertIsNone(payload["rows"][0]["url_title"])


if __name__ == "__main__":
    unittest.main()
