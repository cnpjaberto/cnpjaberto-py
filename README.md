# cnpjaberto

SDK em Python e servidor **Model Context Protocol (MCP)** para o [cnpjaberto.com.br](https://cnpjaberto.com.br), o cadastro aberto de empresas brasileiras (CNPJ). Permite consulta de empresa, grafo de sócios, joins por endereço e contato, estatísticas por CNAE, e panoramas nacional e anual.

```bash
pip install cnpjaberto          # apenas SDK
pip install cnpjaberto[mcp]     # SDK + servidor MCP para Claude Desktop e similares
```

## Início rápido com o SDK

```python
from cnpjaberto import Client

with Client() as cnpj:                       # lê CNPJABERTO_API_KEY do ambiente
    empresa = cnpj.lookup("18.236.120/0001-58")
    print(empresa["razao_social"])

    achados = cnpj.search("nubank", per_page=5)
    for h in achados["results"]:
        print(h["cnpj"], h["razao_social"])

    snap = cnpj.panorama_year(2024)
    print(f"{snap['abertas']:,} abertas, {snap['fechadas']:,} fechadas em 2024")
```

A chave de API é obrigatória. Crie uma conta gratuita em cnpjaberto.com.br/planos, copie sua chave e exporte:

```bash
export CNPJABERTO_API_KEY=sua_chave_aqui
```

## Servidor MCP (Claude Desktop, Cursor, Cline)

Instale o extra e adicione esta config no seu cliente.

```bash
pip install cnpjaberto[mcp]
```

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "cnpjaberto": {
      "command": "cnpjaberto-mcp",
      "env": { "CNPJABERTO_API_KEY": "sua_chave_aqui" }
    }
  }
}
```

Reinicie o Claude Desktop. Agora dá para perguntar coisas como:

* *"Consulta o CNPJ 18.236.120/0001-58 e me diz quando foi fundado."*
* *"Quantas empresas brasileiras abriram em 2024 vs 2023? Quais estados mais cresceram?"*
* *"Acha empresas onde 'Maria Silva' aparece como sócia, agrupando por estado."*
* *"Que outras empresas estão registradas no mesmo endereço da matriz da Magazine Luiza?"*

## Tools expostas

| Tool | O que retorna |
|---|---|
| `lookup_cnpj(cnpj)` | Registro completo: razão social, capital, sócios, com `estabelecimentos[]` (matriz e filiais, endereço, telefones, CNAEs) |
| `list_filiais(cnpj)` | Filiais de uma matriz, paginado, filtro opcional por UF |
| `search_companies(query)` | Busca por razão social, fantasia ou dígitos do CNPJ (mínimo 3 chars) |
| `companies_by_owner(name)` | Empresas onde a pessoa aparece como sócia; `cpf` ajuda a desambiguar homônimos |
| `companies_at_same_address(cep, logradouro, numero)` | Outras empresas registradas no mesmo endereço |
| `companies_by_contact(email \| ddd+telefone)` | Empresas que compartilham o mesmo email ou telefone |
| `cnae_stats(codigo)` | Estatísticas agregadas de um CNAE (contagem, top UFs, top municípios) |
| `panorama_overview()` | Estatísticas nacionais: top UFs e CNAEs, faixas de capital, idade, histórico de 10 anos |
| `panorama_year(year)` | Recorte anual: aberturas e fechamentos, série mensal, fatia MEI |

## Erros tipados

```python
from cnpjaberto import Client, NotFoundError, RateLimitError, AuthError

with Client() as cnpj:
    try:
        cnpj.lookup("00000000000000")
    except NotFoundError:
        ...
    except RateLimitError as e:
        print("Cota diária:", e.payload)
    except AuthError:
        ...
```

## Fonte de dados

Todos os dados vêm do dump público de CNPJ da Receita Federal, atualizado mensalmente. O cnpjaberto.com.br ingere, indexa e serve com lookups sub-segundo, mais joins de valor agregado (grafo de sócios, endereços compartilhados, agregados por CNAE) sobre cerca de 70 milhões de estabelecimentos e 67 milhões de empresas.

## Licença

MIT.
