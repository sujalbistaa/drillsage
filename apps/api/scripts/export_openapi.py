"""Write the API's OpenAPI document to a file (consumed by the web client generator).

Usage: uv run python scripts/export_openapi.py <output.json>
"""

import json
import sys
from pathlib import Path

from drillsage.api.app import create_app


def main() -> None:
    if len(sys.argv) != 2:  # noqa: PLR2004 - exactly one argument
        sys.exit("usage: export_openapi.py <output.json>")
    schema = create_app().openapi()
    Path(sys.argv[1]).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
