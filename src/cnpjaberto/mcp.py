"""MCP (Model Context Protocol) adapter exposing the cnpjaberto client as tools.

Run via the ``cnpjaberto-mcp`` entry point (see ``cli.py``) or directly:

    python -m cnpjaberto.mcp

Requires the ``mcp`` extra: ``pip install cnpjaberto[mcp]``.
"""
from __future__ import annotations

import os

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "The MCP server requires the optional 'mcp' extra:\n"
        "    pip install cnpjaberto[mcp]"
    ) from e

from cnpjaberto.client import Client


def build_server(api_key: str | None = None, base_url: str | None = None) -> FastMCP:
    """Build the MCP server. Tools share a single HTTP client kept warm
    across requests (connection reuse + DNS cache)."""
    mcp = FastMCP(
        "cnpjaberto",
        instructions=(
            "Public CNPJ (Brazilian company registry) data via cnpjaberto.com.br. "
            "Pass digits or formatted CNPJs interchangeably. Auth via the "
            "CNPJABERTO_API_KEY env var raises the daily quota (Pro plan)."
        ),
    )
    client = Client(
        api_key=api_key or os.environ.get("CNPJABERTO_API_KEY"),
        base_url=base_url or os.environ.get("CNPJABERTO_BASE_URL", "https://cnpjaberto.com.br"),
    )

    @mcp.tool()
    def lookup_cnpj(cnpj: str) -> dict:
        """Full company record by CNPJ. Accepts 8, 12, or 14 digits, with or
        without punctuation. Top-level fields include razao_social, capital_social,
        natureza_juridica, simples, socios; estabelecimentos[] holds matriz +
        filiais with situacao_cadastral, address, CNAEs."""
        return client.lookup(cnpj)

    @mcp.tool()
    def list_filiais(cnpj: str, page: int = 1, per_page: int = 50, uf: str | None = None) -> dict:
        """List branches (filiais) of a parent company. Optionally filter by UF."""
        return client.filiais(cnpj, page=page, per_page=per_page, uf=uf)

    @mcp.tool()
    def search_companies(query: str, page: int = 1, per_page: int = 20) -> dict:
        """Search companies by name, fantasy, or CNPJ digits. Query needs ≥ 3 chars;
        per_page capped at 20."""
        return client.search(query, page=page, per_page=per_page)

    @mcp.tool()
    def companies_by_owner(
        name: str,
        cpf: str | None = None,
        exclude: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Find companies where a person appears as partner (sócio). ``cpf`` digits
        (partial OK) disambiguates homonyms."""
        return client.companies_by_owner(name, cpf=cpf, exclude=exclude, limit=limit)

    @mcp.tool()
    def companies_at_same_address(
        cep: str,
        logradouro: str,
        numero: str,
        exclude: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Companies sharing a specific address. CEP must be 8 digits."""
        return client.companies_at_same_address(
            cep, logradouro, numero, exclude=exclude, limit=limit,
        )

    @mcp.tool()
    def companies_by_contact(
        email: str | None = None,
        ddd: str | None = None,
        telefone: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Find companies sharing a contact. Pass email OR (ddd AND telefone)."""
        return client.companies_by_contact(
            email=email, ddd=ddd, telefone=telefone, limit=limit,
        )

    @mcp.tool()
    def cnae_stats(codigo: str) -> dict:
        """Aggregate stats for a CNAE (economic activity code): total companies,
        top UFs, top municipalities."""
        return client.cnae_stats(codigo)

    @mcp.tool()
    def panorama_overview() -> dict:
        """National statistics: total active companies, top UFs and CNAEs,
        capital social ranges, age buckets, 10-year history."""
        return client.panorama_overview()

    @mcp.tool()
    def panorama_year(year: int) -> dict:
        """Yearly snapshot: openings/closings, monthly series, top CNAEs and UFs, MEI share."""
        return client.panorama_year(year)

    return mcp


def main() -> None:
    """Run the server on stdio (default transport for Claude Desktop)."""
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
