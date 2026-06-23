import json
import tempfile
import unittest
from pathlib import Path

from research_os.cleanup import build_legacy_delete_plan


class LegacyCleanupTest(unittest.TestCase):
    def test_build_legacy_delete_plan_uses_only_previous_artifact_keys(self):
        payload = {
            "created": [
                {"key": "genres", "database_id": "db-genres"},
                {"key": "queries", "database_id": "db-queries"},
                {"key": "template_bank", "database_id": "db-template"},
                {"key": "operation_results", "database_id": "db-results"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "notion-create-result.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            plan = build_legacy_delete_plan(path)

        self.assertEqual([item.database_id for item in plan.items], ["db-genres", "db-queries", "db-results"])
        self.assertEqual(plan.skipped_keys, ["template_bank"])


if __name__ == "__main__":
    unittest.main()
