"""Install pinned cspell data without npm lifecycle scripts; preserve package licenses."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import urlopen


def install(output: Path, selected: list[str]) -> None:
    lock = json.loads(Path(__file__).with_name("dictionaries.lock.json").read_text())
    unknown = set(selected) - {row["id"] for row in lock}
    if unknown:
        raise ValueError(f"Unknown dictionaries: {unknown}")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".dictionaries-") as temp:
        stage = Path(temp) / "data"
        stage.mkdir()
        manifest = {}
        for row in lock:
            if selected and row["id"] not in selected:
                continue
            with urlopen(row["url"], timeout=60) as response:
                data = response.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise ValueError("Dictionary download exceeds budget")
            directory = stage / row["id"]
            directory.mkdir()
            destination = directory / row["file"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            if "integrity" in row:
                expected = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
                if expected != row["integrity"]:
                    raise ValueError(f"Archive integrity failed: {row['id']}")
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                    member = archive.getmember("package/" + row["file"])
                    if not member.isfile() or member.size > 128 * 1024 * 1024:
                        raise ValueError("Invalid dictionary artifact")
                    stream = archive.extractfile(member)
                    assert stream is not None
                    destination.write_bytes(stream.read())
                    for member in archive.getmembers():
                        if member.isfile() and "license" in member.name.lower():
                            path = Path(member.name)
                            if ".." in path.parts or path.is_absolute():
                                raise ValueError("Invalid license path")
                            license_path = directory / "licenses" / path
                            license_path.parent.mkdir(parents=True, exist_ok=True)
                            stream = archive.extractfile(member)
                            assert stream is not None
                            license_path.write_bytes(stream.read())
            else:
                if hashlib.sha256(data).hexdigest() != row["sha256"]:
                    raise ValueError("Raw dictionary integrity failed")
                destination.write_bytes(data)
            manifest[row["id"]] = dict(row, file=str(destination.relative_to(stage)),
                                        sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
            print(f"Installed {row['id']}", flush=True)
        (stage / "installed.json").write_text(json.dumps(manifest, indent=2) + "\n")
        shutil.move(str(stage), output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dictionary", action="append", default=[])
    args = parser.parse_args()
    install(args.output, args.dictionary)
