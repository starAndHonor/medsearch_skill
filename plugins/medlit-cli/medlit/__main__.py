"""Allow running medlit as a module: python -m medlit.cli."""

from medlit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
