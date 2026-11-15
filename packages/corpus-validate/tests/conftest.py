"""Test archives retain whitespace required by Text-Fabric features."""

from pathlib import Path
from zipfile import ZipFile

import pytest


@pytest.fixture(scope="session")
def spanning_fixture(tmp_path_factory):
    root = tmp_path_factory.mktemp("tf-spanning")
    with ZipFile(Path(__file__).parent / "fixtures" / "spanning-mini.zip") as archive:
        archive.extractall(root)
    return root
