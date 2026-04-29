"""Console-script entry points declared in pyproject.toml."""
from __future__ import annotations


def run_mcp() -> None:
    """Entry point for the ``cnpjaberto-mcp`` console script."""
    from cnpjaberto.mcp import main
    main()
