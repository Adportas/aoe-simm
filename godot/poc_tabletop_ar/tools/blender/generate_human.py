"""Compatibility entry point for the frontier guard asset generator."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_frontier_guard import main  # noqa: E402


if __name__ == "__main__":
    main()
