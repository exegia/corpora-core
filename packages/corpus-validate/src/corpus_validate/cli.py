"""JSON CLI boundary for validating a trusted local upload staging file."""

import argparse
import json
import sys
from pathlib import Path

from .validator import MAX_ARCHIVE_BYTES, ArchiveTooLarge, UnsupportedFormat, validate_archive


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one bounded corpus archive")
    parser.add_argument("path", type=Path, help="local archive staged by the caller")
    parser.add_argument("--name", help="public filename to report instead of the staging path")
    args = parser.parse_args()
    try:
        if args.path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ArchiveTooLarge(f"Archive exceeds {MAX_ARCHIVE_BYTES} bytes")
        result = validate_archive(args.path.read_bytes(), args.name or args.path.name)
    except (ArchiveTooLarge, UnsupportedFormat) as error:
        print(json.dumps({"error": str(error), "code": error.code}))
        return 2
    except OSError as error:
        print(json.dumps({"error": f"Could not read archive: {error}", "code": "unreadable"}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
