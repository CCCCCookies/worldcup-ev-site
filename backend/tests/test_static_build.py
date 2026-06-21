import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_static_dashboard import keep_previous_dashboard_if_refresh_failed


class StaticBuildTests(unittest.TestCase):
    def test_failed_refresh_keeps_previous_valid_dashboard(self):
        failed = {
            "status": {
                "stale": True,
                "polyalpha_generated_at": "",
                "sporttery_last_update": "",
                "errors": ["network failed"],
            },
            "staticMode": True,
        }
        previous = {
            "status": {
                "stale": False,
                "polyalpha_generated_at": "2026-06-21T13:30",
                "sporttery_last_update": "2026-06-21 17:31:24",
                "errors": [],
            },
            "staticMode": True,
        }

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dashboard.json"
            output.write_text(json.dumps(previous), encoding="utf-8")

            selected = keep_previous_dashboard_if_refresh_failed(failed, output)

        self.assertEqual(selected["status"]["polyalpha_generated_at"], "2026-06-21T13:30")
        self.assertEqual(selected["status"]["sporttery_last_update"], "2026-06-21 17:31:24")
        self.assertTrue(selected["status"]["stale"])
        self.assertIn("network failed", selected["status"]["errors"])


if __name__ == "__main__":
    unittest.main()
