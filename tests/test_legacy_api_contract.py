"""Keep the pinned legacy REST inventory complete and internally consistent."""

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "contracts" / "legacy-api"
METHODS = {"get", "post", "put", "patch", "delete"}
SOURCE_REVISION = "d9c6e3d32b825eb7a5ac75114eaeb249821df2a2"
OWNERS = {
    "platform": "corpora-api",
    "ingestion": "corpora-source",
    "validation": "corpora-fabric",
    "storage": "corpora-source",
    "corpus_fabric": "corpora-fabric",
    "references": "corpora-fabric",
    "linking": "proposed:corpora-linking",
    "ai_curation": "proposed:corpora-curation",
}
SOURCE_MODULES = {
    "Ingestion": "packages/admin/src/admin/services/ingest_api.py",
    "Validation": "packages/admin/src/admin/services/validation_api.py",
    "Storage": "packages/admin/src/admin/services/storage_api.py",
    "Corpus Detail": "packages/admin/src/admin/services/corpus_detail_api.py",
    "References": "packages/admin/src/admin/services/reference_api.py",
    "linking": "src/corpora_py/linking_api.py",
    "AI Curation": "src/corpora_py/ai/router.py",
    "Health": "src/corpora_py/app.py",
}


def expected_ticket(method: str, path: str) -> str:
    if path in {"/health", "/capabilities"}:
        return "03"
    if path.startswith("/ingest"):
        return "05"
    if path == "/validate":
        return "04"
    if path.startswith("/storage/") and any(
        part in path for part in ("/manifest", "/nodes/", "/versions", "/restore", "/index", "/sections", "/content")
    ):
        return "09" if method == "PATCH" or path.endswith(("/versions", "/restore")) else "08"
    if path.startswith("/storage"):
        return "07" if method in {"POST", "DELETE"} else "06"
    if path.startswith("/refs"):
        return "10"
    if path.startswith("/linking"):
        if "/discoveries" in path:
            return "13"
        if "/references" in path:
            return "11"
        if path.endswith(("/conversion-events", "/scholarly-conversion-events", "/import-plan", "/import", "/export-cusx")):
            return "14"
        return "12"
    if path in {"/ai/providers", "/ai/validate"}:
        return "15"
    if path == "/ai/chat" or path.startswith("/ai/threads"):
        return "18"
    if path.startswith(("/ai/suggestions", "/ai/changes")):
        return "19"
    if path.startswith("/ai/drafts"):
        if path.endswith(("/manifest", "/index", "/versions", "/sections", "/content")) or "/nodes/" in path:
            return "17"
        return "16"
    raise AssertionError(f"Unmapped legacy route: {method} {path}")


class LegacyApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        snapshot = (ROOT / "openapi.json").read_bytes()
        cls.spec = json.loads(snapshot)
        cls.manifest = json.loads((ROOT / "operations.json").read_text())
        cls.snapshot_hash = hashlib.sha256(snapshot).hexdigest()

    def test_snapshot_and_operation_partition(self) -> None:
        self.assertEqual(self.manifest["snapshot_sha256"], self.snapshot_hash)
        self.assertEqual(self.manifest["source_repo"], "exegia/corpora-py")
        self.assertEqual(self.manifest["source_revision"], SOURCE_REVISION)
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
                self.assertEqual(row["proposed_owner"], OWNERS[row["domain"]])
                self.assertEqual(row["ticket"], expected_ticket(row["method"], row["legacy_path"]))
                source = SOURCE_MODULES[operation["tags"][0]]
                if row["legacy_path"].startswith("/ai/drafts"):
                    source = "src/corpora_py/ai/draft_router.py"
                self.assertEqual(row["source_module"], source)
                self.assertIn(row["legacy_auth"], {"public", "supabase_jwt_when_auth_required"})
                self.assertIsInstance(row["state_dependencies"], list)
                self.assertTrue(row["route_identity_policy"])
                self.assertIsInstance(row["runtime_error_statuses"], list)
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
        self.assertIn(501, ai["/ai/chat"]["runtime_error_statuses"])
        self.assertIn(501, ai["/ai/drafts"]["runtime_error_statuses"])
        linking = [row for row in self.manifest["operations"] if row["legacy_path"].startswith("/linking")]
        self.assertEqual(len(linking), 15)
        self.assertTrue(all(row["route_identity_policy"] == "bearer_required_even_if_global_auth_disabled" for row in linking))
        restore = next(row for row in self.manifest["operations"] if row["legacy_path"] == "/storage/{filename}/restore")
        self.assertIn(501, restore["runtime_error_statuses"])
        self.assertEqual(restore["state_dependencies"], ["read_only_policy", "not_implemented"])


if __name__ == "__main__":
    unittest.main()
