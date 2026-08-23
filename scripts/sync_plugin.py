"""Verify that repository entrypoints resolve to the plugin-owned runtime.

This filename is retained for compatibility with earlier development notes.
There is intentionally no copy/synchronization operation: plugin source is the
single implementation and repository entrypoints delegate to it.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "medlit-cli"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the plugin-owned MedLit runtime.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Accepted for compatibility; verification is always read-only.",
    )
    parser.parse_args()

    required = (
        PLUGIN_ROOT / ".codex-plugin" / "plugin.json",
        PLUGIN_ROOT / "scripts" / "medlit_cli.py",
        PLUGIN_ROOT / "medlit" / "cli.py",
        PLUGIN_ROOT / "medlit" / "pubmed" / "query.py",
        PLUGIN_ROOT / "medlit" / "retrieval" / "fusion.py",
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        for path in missing:
            print(f"missing: {path.relative_to(ROOT)}")
        return 1

    sys.path.insert(0, str(ROOT))
    module = importlib.import_module("medlit.pubmed.query")
    resolved = Path(module.__file__).resolve()
    try:
        resolved.relative_to(PLUGIN_ROOT.resolve())
    except ValueError:
        print(f"repository import escaped plugin runtime: {resolved}")
        return 1

    print(f"Plugin runtime is the sole active source: {resolved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
