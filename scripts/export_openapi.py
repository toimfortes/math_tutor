from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend/openapi.json"
sys.path.insert(0, str(ROOT))

from backend.app.main import create_app  # noqa: E402


def main() -> None:
    schema = create_app().openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
