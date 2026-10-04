"""Entry points dos console_scripts declarados no pyproject.toml."""

from __future__ import annotations


def run_mcp() -> None:
    """Entry point do console_script ``cnpjaberto-mcp``."""
    from cnpjaberto.mcp import main

    main()
