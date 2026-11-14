"""The generated Python envelope keeps the legacy graph.json wire contract."""

import unittest

from corpora_schema_types import GraphValidationError, validate_graph


def graph_dict() -> dict:
    return {
        "schemaVersion": "1.0.0",
        "work": {
            "schemaVersion": "1.0.0",
            "id": "e36203da-956d-4a15-8534-d2c847e884ba",
            "corpusId": "26b0c5be-751d-4299-ae2e-31a08cdd206b",
            "slug": "sample",
            "title": "Sample",
        },
        "edition": {
            "schemaVersion": "1.0.0",
            "id": "e2d0beaf-7dcb-4f4b-a591-8a53d35d055d",
            "workId": "e36203da-956d-4a15-8534-d2c847e884ba",
            "slug": "sample",
            "title": "Sample",
            "language": "en",
        },
        "sourceAsset": {
            "schemaVersion": "1.0.0",
            "id": "6ae74f15-e9ca-4ac2-9471-f459a0f864af",
            "editionId": "e2d0beaf-7dcb-4f4b-a591-8a53d35d055d",
            "sourceFormat": "plain",
        },
        "nodes": [],
        "fragments": [],
    }


class CanonicalGraphTests(unittest.TestCase):
    def test_preserves_legacy_camel_case_keys_and_omits_absent_corpus(self) -> None:
        payload = graph_dict()
        self.assertEqual(validate_graph(payload).to_wire(), payload)

    def test_rejects_missing_entity_and_invalid_node(self) -> None:
        payload = graph_dict()
        del payload["work"]
        with self.assertRaises(GraphValidationError):
            validate_graph(payload)
        payload = graph_dict()
        payload["nodes"] = [{"schemaVersion": "1.0.0", "category": "invalid"}]
        with self.assertRaises(GraphValidationError):
            validate_graph(payload)


if __name__ == "__main__":
    unittest.main()
