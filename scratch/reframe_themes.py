"""Compatibility wrapper for the content-safety scanner."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.content_pipeline.safety import main


if __name__ == "__main__":
    main()
