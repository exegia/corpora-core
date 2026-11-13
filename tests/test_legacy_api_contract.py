"""Keep the pinned legacy REST inventory complete and internally consistent."""

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "contracts" / "legacy-api"
METHODS = {"get", "post", "put", "patch", "delete"}


class LegacyApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        snapshot = (ROOT / "openapi.json").read_bytes()
        cls.spec = json.loads(snapshot)
        cls.manifest = json.loads((ROOT / "operations.json").read_text())
        cls.snapshot_hash = hashlib.sha256(snapshot).hexdigest()

    def test_snapshot_and_operation_partition(self) -> None:
        self.assertEqual(self.manifest["snapshot_sha256"], self.snapshot_hash)
        actual = {
            (method.upper(), path, operation["operationId"])
            for path, methods in self.spec["paths"].items()
            for method, operation in methods.items()
            if method in METHODS
        }
        included = {
            (item["method"], item["legacy_path"], item["operation_id"])
            for item in self.manifest["operations"]
        }
        excluded = {
            (item["method"], item["path"], item["operation_id"])
            for item in self.manifest["excluded_operations"]
        }
        self.assertEqual((len(actual), len(included), len(excluded)), (77, 63, 14))
        self.assertEqual(actual, included | excluded)
        self.assertFalse(included & excluded)
        self.assertTrue(all(path.startswith("/convert") for _, path, _ in excluded))
        self.assertTrue(all(not path.startswith("/convert") for _, path, _ in included))

    def test_every_mapping_has_contract_and_runtime_owner(self) -> None:
        mapped = self.manifest["operations"]
        self.assertEqual(len({(row["method"], row["target_path"]) for row in mapped}), 63)
        self.assertEqual(len({row["operation_id"] for row in mapped}), 63)
        for row in mapped:
            with self.subTest(operation=row["operation_id"]):
                self.assertEqual(row["target_path"], "/v1" + row["legacy_path"])
                operation = self.spec["paths"][row["legacy_path"]][row["method"].lower()]
                pointer = "#/paths/" + row["legacy_path"].replace("~", "~0").replace("/", "~1")
                self.assertEqual(row["openapi_operation_pointer"], pointer + "/" + row["method"].lower())
                statuses = sorted(operation["responses"], key=lambda v: (int(v) if v.isdigit() else 999, v))
                self.assertEqual(row["documented_response_statuses"], statuses)
                self.assertEqual(
                    row["documented_error_statuses"],
                    [status for status in statuses if status.isdigit() and int(status) >= 400],
                )
                self.assertTrue(row["domain"])
                self.assertTrue(row["ticket"])
                self.assertTrue(row["source_module"])
                self.assertIn(row["legacy_auth"], {"public", "supabase_jwt_when_auth_required"})
                self.assertIsInstance(row["state_dependencies"], list)
                self.assertEqual(
                    row["target_status"],
                    "existing" if row["target_path"] == "/v1/health" else "proposed",
                )

    def test_scope_decisions_are_explicit(self) -> None:
        paths = {row["legacy_path"] for row in self.manifest["operations"]}
        self.assertIn("/ingest", paths)
        self.assertIn("/linking/{space_id}/conversion-events", paths)
        self.assertIn("/linking/{space_id}/scholarly-conversion-events", paths)
        public = {"/health", "/capabilities"}
        self.assertEqual(
            {row["legacy_path"] for row in self.manifest["operations"] if row["legacy_auth"] == "public"},
            public,
        )
        ai = {row["legacy_path"]: row for row in self.manifest["operations"] if row["legacy_path"].startswith("/ai/")}
        self.assertIn("not_implemented", ai["/ai/chat"]["state_dependencies"])
        self.assertIn("owner_scoped_thread_store", ai["/ai/threads/{thread_id}"]["state_dependencies"])
        self.assertIn("owner_scoped_drafts", ai["/ai/drafts/{draft_id}"]["state_dependencies"])


if __name__ == "__main__":
    unittest.main()
