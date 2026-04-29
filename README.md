# cnpjaberto

Python SDK and **Model Context Protocol (MCP)** server for [cnpjaberto.com.br](https://cnpjaberto.com.br) — an open registry of every Brazilian company (CNPJ), with company lookup, partnership graphs, address/contact joins, CNAE statistics, and national/yearly panoramas.

```bash
pip install cnpjaberto          # SDK only
pip install cnpjaberto[mcp]     # SDK + MCP server for Claude Desktop & friends
```

## SDK quickstart

```python
from cnpjaberto import Client

with Client() as cnpj:                       # reads CNPJABERTO_API_KEY from env
    company = cnpj.lookup("18.236.120/0001-58")
    print(company["razao_social"])

    hits = cnpj.search("nubank", limit=5)
    for h in hits["results"]:
        print(h["cnpj_basico"], h["razao_social"])

    snap = cnpj.panorama_year(2024)
    print(f"{snap['abertas']:,} opened, {snap['fechadas']:,} closed")
```

Anonymous calls work and are subject to the public rate limit. For the daily quota tier, sign up at cnpjaberto.com.br/planos and export your key:

```bash
export CNPJABERTO_API_KEY=your_key_here
```

## MCP server (Claude Desktop, Cursor, Cline, etc.)

Install the extra and add this to your client config:

```bash
pip install cnpjaberto[mcp]
```

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "cnpjaberto": {
      "command": "cnpjaberto-mcp",
      "env": { "CNPJABERTO_API_KEY": "your_key_here" }
    }
  }
}
```

Restart Claude Desktop. You can now ask things like:

- *"Look up CNPJ 18.236.120/0001-58 and tell me when it was founded."*
- *"Find Brazilian bakeries (CNAE 1091-1/02) — show top UFs."*
- *"How many companies opened in 2024 vs 2023?"*
- *"Which companies share the same address as Nubank's HQ?"*

## Tools exposed

| Tool | What it returns |
|---|---|
| `lookup_cnpj(cnpj)` | Full record: razao_social, capital, partners, plus `estabelecimentos[]` (matriz + filiais with address, phones, CNAEs) |
| `list_filiais(cnpj)` | Branches of a parent company, paginated, optional UF filter |
| `search_companies(query)` | Search by name, fantasy name, or CNPJ digits (≥3 chars) |
| `companies_by_owner(name)` | Companies where a person appears as partner; `cpf` digits disambiguate homonyms |
| `companies_at_same_address(cep, logradouro, numero)` | Other companies registered at the same exact address |
| `companies_by_contact(email \| ddd+telefone)` | Companies sharing the same email or phone |
| `cnae_stats(codigo)` | Aggregate stats for a CNAE (count, top UFs, top municipalities) |
| `panorama_overview()` | National stats: top UFs/CNAEs, capital ranges, age buckets, 10y history |
| `panorama_year(year)` | Yearly snapshot: openings/closings, monthly series, MEI share |

## Errors

The SDK raises typed exceptions:

```python
from cnpjaberto import Client, NotFoundError, RateLimitError, AuthError

with Client() as cnpj:
    try:
        cnpj.lookup("00000000000000")
    except NotFoundError:
        ...
    except RateLimitError as e:
        print("Daily quota:", e.payload)
    except AuthError:
        ...
```

## Data source

All data comes from the Brazilian Federal Revenue (Receita Federal) public CNPJ dump, refreshed monthly. cnpjaberto.com.br ingests, indexes, and serves it with sub-second lookups, plus value-added joins (partnership graphs, shared addresses, CNAE aggregates) computed over ~70M establishments and ~67M companies.

## Roadmap

- [ ] `companies_in_city` and other Pro-tier endpoints (currently the API gates these by JWT only; once X-API-Key Pro is honored on the backend, they ship in v0.2)
- [ ] Async client (`AsyncClient`)
- [ ] Hosted MCP at `mcp.cnpjaberto.com.br` (HTTP+SSE) — no local install
- [ ] NPM package mirroring the same surface
- [ ] Streaming endpoints for bulk export

## Contributing

Issues and PRs welcome at [github.com/iagoassis-dev/cnpjaberto-py](https://github.com/iagoassis-dev/cnpjaberto-py).

## License

MIT.
