"""Adapter Model Context Protocol (MCP) que expõe o cliente cnpjaberto como tools.

Rode pelo console_script ``cnpjaberto-mcp`` (definido em ``cli.py``) ou direto:

    python -m cnpjaberto.mcp

Requer o extra ``mcp``: ``pip install cnpjaberto[mcp]``.
"""
from __future__ import annotations

import os

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "O servidor MCP requer o extra opcional 'mcp':\n"
        "    pip install cnpjaberto[mcp]"
    ) from e

from cnpjaberto.client import Client


def build_server(api_key: str | None = None, base_url: str | None = None) -> FastMCP:
    """Constrói o servidor MCP. As tools compartilham um único cliente HTTP
    quente entre requisições (reuso de conexão e cache de DNS)."""
    mcp = FastMCP(
        "cnpjaberto",
        instructions=(
            "Dados públicos de CNPJ (cadastro de empresas brasileiras) via "
            "cnpjaberto.com.br. Aceita CNPJ em dígitos ou formatado. A "
            "variável CNPJABERTO_API_KEY libera a cota diária do plano Pro."
        ),
    )
    client = Client(
        api_key=api_key or os.environ.get("CNPJABERTO_API_KEY"),
        base_url=base_url or os.environ.get("CNPJABERTO_BASE_URL", "https://cnpjaberto.com.br"),
    )

    @mcp.tool()
    def lookup_cnpj(cnpj: str) -> dict:
        """Registro completo de uma empresa pelo CNPJ. Aceita 8, 12 ou 14
        dígitos, com ou sem pontuação. No topo retorna razao_social,
        capital_social, natureza_juridica, simples, socios. A lista
        estabelecimentos[] traz matriz e filiais, com situacao_cadastral,
        endereço e CNAEs."""
        return client.lookup(cnpj)

    @mcp.tool()
    def list_filiais(cnpj: str, page: int = 1, per_page: int = 50, uf: str | None = None) -> dict:
        """Lista as filiais de uma matriz. Opcionalmente filtra por UF."""
        return client.filiais(cnpj, page=page, per_page=per_page, uf=uf)

    @mcp.tool()
    def search_companies(query: str, page: int = 1, per_page: int = 20) -> dict:
        """Busca empresas por razão social, fantasia ou dígitos do CNPJ.
        A query precisa de no mínimo 3 caracteres; per_page é limitado a 20."""
        return client.search(query, page=page, per_page=per_page)

    @mcp.tool()
    def companies_by_owner(
        name: str,
        cpf: str | None = None,
        exclude: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Acha empresas onde uma pessoa aparece como sócia. ``cpf`` em
        dígitos (parcial é aceito) ajuda a desambiguar homônimos."""
        return client.companies_by_owner(name, cpf=cpf, exclude=exclude, limit=limit)

    @mcp.tool()
    def companies_at_same_address(
        cep: str,
        logradouro: str,
        numero: str,
        exclude: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Empresas que compartilham um endereço específico. CEP exige 8 dígitos."""
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
        """Acha empresas que compartilham um contato. Informe email OU (ddd E telefone)."""
        return client.companies_by_contact(
            email=email, ddd=ddd, telefone=telefone, limit=limit,
        )

    @mcp.tool()
    def cnae_stats(codigo: str) -> dict:
        """Estatísticas agregadas de um CNAE: total de empresas, top UFs,
        top municípios."""
        return client.cnae_stats(codigo)

    @mcp.tool()
    def panorama_overview() -> dict:
        """Estatísticas nacionais: total de empresas ativas, top UFs e CNAEs,
        faixas de capital social, faixas etárias, histórico de 10 anos."""
        return client.panorama_overview()

    @mcp.tool()
    def panorama_year(year: int) -> dict:
        """Snapshot anual: aberturas, fechamentos, série mensal, top CNAEs e
        UFs, fatia MEI."""
        return client.panorama_year(year)

    return mcp


def main() -> None:
    """Roda o servidor por stdio (transport padrão do Claude Desktop)."""
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
