#!/usr/bin/env python3
"""Generate OpenAPI specification from FastAPI app."""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app


def main():
    """Generate and save OpenAPI spec."""
    openapi_spec = app.openapi()

    # Output to stdout or file
    output_path = Path(__file__).parent.parent / "docs" / "openapi.json"
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(openapi_spec, f, indent=2)

    print(f"OpenAPI spec written to {output_path}")


if __name__ == "__main__":
    main()
