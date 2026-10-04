# cnpjaberto

SDK Python e servidor **Model Context Protocol (MCP)** para o [CNPJ Aberto](https://cnpjaberto.com.br). A versão 0.2.0 oferece **44 ferramentas**: consulta cadastral, busca avançada, prospecção, vínculos societários, recursos PRO, compliance, panoramas publicados e catálogos B3/CVM.

Python 3.10+. O SDK é síncrono; o servidor MCP executa as consultas em workers para não bloquear o protocolo.

```bash
pip install cnpjaberto
pip install 'cnpjaberto[mcp]'
export CNPJABERTO_API_KEY=sua_chave_aqui
```

Crie sua chave na conta do CNPJ Aberto. Todas as consultas de integração usam `X-API-Key` e consomem a cota da conta. O servidor determina acesso, cotas e vigência do plano; o SDK não fixa valores de cota nem presume que uma chave tenha PRO.

## SDK

```python
from cnpjaberto import Client

with Client() as cnpj:
    empresa = cnpj.lookup("18.236.120/0001-58")
    print(empresa["razao_social"])
    # Com API key, contém apenas o estabelecimento solicitado.
    print(empresa["estabelecimentos"])

    filiais = cnpj.filiais("18236120000158", uf="SP", q="centro", per_page=200)
    busca = cnpj.search("nubank", per_page=5)
    cidades = cnpj.search_municipalities("São Paulo", uf="SP")
    empresas = cnpj.advanced_search(
        uf="SP", municipio_codigo="7107", cnae="6201501", mei=False,
    )
    panorama = cnpj.panorama_year(2025, sem_mei=True)
```

PRO usa a mesma chave da conta, sem um modo especial:

```python
from cnpjaberto import Client, ProRequiredError

with Client() as cnpj:
    try:
        dossie = cnpj.compliance_dossier("18236120000158")
        grupo = cnpj.business_group("18236120000158")
        cruzamento = cnpj.common_owners(["18236120", "00000000"])
        leads = cnpj.leads("SP", "7107", com_email=True)
    except ProRequiredError as error:
        print(error.payload)  # detalhe do backend, incluindo upgrade_url quando presente
```

Os nomes dos parâmetros novos acompanham a API (`nome`, `municipio_codigo`, `sem_mei`, etc.). Os parâmetros legados continuam disponíveis, como `companies_by_owner(name=...)` e `search(q=...)`. Métodos retornam o JSON original, incluindo indicadores de prévia/bloqueio. `search_cnaes`, `search_municipalities` e `municipalities` retornam listas; `panorama_csv` retorna texto CSV.

`Client(api_key=..., base_url=..., timeout=30)` permite configuração explícita. Um `httpx.Client` injetado com `client=...` pertence ao chamador e não será fechado pelo SDK; o transporte mantém sua configuração de timeout. O SDK aplica sua base URL e chave mesmo ao transporte injetado. Clientes criados pelo SDK são fechados no `with` ou em `close()`.

## Servidor MCP

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

Use o caminho absoluto do executável se o aplicativo não o encontrar no PATH. Também é possível executar `python -m cnpjaberto.mcp`. O transporte é **stdio**; stdout fica reservado ao JSON-RPC. `CNPJABERTO_BASE_URL` substitui a URL padrão no servidor MCP. Credenciais são configuração do processo, nunca argumentos das ferramentas.

O recurso `cnpjaberto://guide` descreve autenticação, planos, cotas e interpretação dos dados. Todas as ferramentas consultam dados, inclusive o POST de resumos em lote, e têm anotações MCP de leitura. Cada chamada pode consumir cota. Não há repetição automática de chamadas HTTP. O cliente compartilhado é fechado no encerramento, inclusive quando a sessão é cancelada.

O extra MCP mantém a linha compatível `mcp>=1.28,<2`, conforme a [orientação oficial para v1](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x). O SDK HTTP continua utilizável sem esse extra.

## Ferramentas e métodos

Os nomes MCP coincidem com os métodos do SDK, exceto `lookup_cnpj` → `lookup`, `list_filiais` → `filiais` e `search_companies(query=...)` → `search(q=...)`.

| Ferramenta | Contrato |
|---|---|
| `lookup_cnpj` | Consulta CNPJ completo (14 caracteres, numérico ou alfanumérico). Com API key, estabelecimentos contém apenas o estabelecimento solicitado. Use filiais para paginar os demais. Sócios e demais campos são preservados. |
| `list_filiais` | Filiais por CNPJ completo; filtro UF e busca textual q. Página/tamanho: 1–200. |
| `companies_by_owner` | Empresas onde a pessoa aparece como sócia. ``cpf`` em dígitos (parcial é aceito) ajuda a desambiguar homônimos; ``exclude`` remove um ``cnpj_basico`` específico do resultado. |
| `companies_at_same_address` | PRO: empresas registradas no mesmo endereço (CEP, logradouro, número). ``cep`` precisa ter exatamente 8 dígitos, sem traço. |
| `companies_by_contact` | PRO: empresas que compartilham um contato. Informe ``email`` OU (``ddd`` E ``telefone``); a busca por telefone exige o DDD separado. |
| `cnae_stats` | Estatísticas agregadas de um CNAE (contagem, top UFs, etc.). |
| `panorama_overview` | Panorama nacional: totais, top UFs, top CNAEs, faixas de capital. |
| `panorama_year` | Recorte anual: aberturas, fechamentos, série mensal, top CNAEs e UFs. |
| `owner_summary` | Resumo das empresas de um sócio; CPF parcial ajuda a desambiguar homônimos. |
| `owner_summaries` | Resumo em lote de até 10.000 sócios (nome e cpf opcional). A ordem dos resultados corresponde à ordem de items. Consulta sem escrita. |
| `participations` | PRO: empresas que têm este CNPJ como sócio pessoa jurídica. |
| `cnae_catalog` | Catálogo CNAE; secao opcional A–U. Sem seção, retorna todo o catálogo. |
| `control_tree` | PRO: árvore de controle societário da empresa. |
| `common_owners` | PRO: cruza sócios de 2 ou mais raízes distintas. modo: intersecao ou sobreposicao; min_empresas: 2–50. |
| `advanced_search` | Busca por filtros combinados. Informe pelo menos um filtro seletivo. UF aceita até 5 estados separados por vírgula; CNAE, situação e porte também aceitam vírgulas. Contato/endereço exato e filtros com_email/com_telefone exigem PRO. Prefira municipio_codigo e municipio_uf ao nome parcial. |
| `competitors` | Até 8 concorrentes da empresa; o backend não aceita parâmetro limit. |
| `person_profile` | Raio-X da pessoa por nome e CPF parcial. Free retorna prévia; PRO retorna análise completa. Preserve os indicadores de bloqueio da resposta. |
| `search_owners` | Busca sócios por nome ou CPF/CNPJ. Exige nome ou documento; refine nomes amplos com sobrenome ou cidade. faixa_etaria aceita códigos 1–9 separados por vírgula. |
| `owner_suggestions` | Sugestões de sócios e MEI/EI por nome (mínimo 3 caracteres). |
| `leads` | Prospecção por UF e município obrigatórios. Resolva municipio_codigo com search_municipalities. Free mascara contatos (contact_gated); PRO libera contato. Não trate valores mascarados como contatos reais. Datas de abertura em YYYY-MM-DD. |
| `search_cnaes` | Busca código ou descrição CNAE; retorna lista de código e descrição. |
| `search_municipalities` | Busca nome de município, opcionalmente por UF. Retorna códigos para leads e advanced_search. |
| `municipalities` | Municípios de uma UF com códigos e descrições; retorna lista. |
| `companies_by_city` | PRO: empresas do município (código), com busca por nome, logradouro e bairro. |
| `service_catalog` | Catálogo de serviços com slugs para search_services. |
| `search_services` | Empresas por slug de serviço, UF e código de município. sem_mei exclui MEIs. |
| `business_group` | PRO: mapa do grupo empresarial por vínculos societários. Mapas amplos podem retornar 503. |
| `red_flags` | Indicadores cadastrais de atenção da empresa. São sinais para análise, não prova de irregularidade. |
| `ownership_network` | Rede societária por nome ou CPF. Use cpf parcial para reduzir homônimos; refine buscas amplas. |
| `compliance_summary` | Resumo de sanções diretas e dívida ativa da própria pessoa jurídica; sem PEP de sócios. |
| `compliance_dossier` | PRO: dossiê de sanções públicas, PEP dos sócios e indicadores de atenção. |
| `active_debt` | Dívida ativa PGFN. encontrado=false é resultado válido, não erro 404. |
| `panorama_catalog` | Catálogo de períodos e edições publicados; use antes de solicitar relatórios. |
| `panorama_report` | Relatório publicado por período, UF (BR por padrão), recorte, tema e edição. Consulte panorama_catalog para valores disponíveis. |
| `panorama_csv` | CSV do relatório publicado; retorna texto, não JSON. tabela padrão cnaes. Consulte panorama_catalog para períodos e recortes disponíveis. |
| `panorama_revisions` | Revisões publicadas de um período do panorama. |
| `panorama_alphanumeric` | Painel de CNPJs alfanuméricos: totais e série mensal do ano solicitado. |
| `stock_catalog` | Catálogo B3; tipo opcional ACAO, FII, BDR, UNT ou ETF. |
| `stock_ticker` | Detalhe de ticker B3, incluindo fundo para FII e tickers relacionados. |
| `fund_catalog` | Catálogo CVM: FII, FIF, FIDC, FIP, FIAGRO ou FIIM. situacao=all inclui fundos inativos. |
| `fund` | Detalhe de fundo CVM por CNPJ numérico completo. |
| `funds_by_auditor` | Outros fundos ativos auditados pela mesma firma, ordenados por patrimônio. |
| `similar_funds` | Fundos similares por categoria e patrimônio líquido. |
| `search_companies` | Busca por razão social, fantasia ou dígitos do CNPJ. ``q`` exige no mínimo 4 caracteres; ``per_page`` é limitado a 20. |

## Planos e limites de integração

- **PRO:** endereço/contato compartilhado, participações, grupo empresarial, árvore de controle, sócios em comum, empresas por cidade e dossiê de compliance. O backend também reconhece planos Starter ativos conforme suas regras de vigência.
- **Busca avançada:** filtros usuais disponíveis no Free; presença ou valor de e-mail/telefone e endereço exato exigem PRO.
- **Leads:** UF e código de município são obrigatórios. Free recebe contatos mascarados e `contact_gated`; PRO recebe contatos disponíveis na base. Não use os valores mascarados como dados reais.
- **Raio-X:** Free recebe prévia; PRO recebe a análise completa. O SDK preserva a resposta e seus indicadores de bloqueio.
- **Limites:** busca textual exige 4 caracteres, páginas 1–50 e até 20 resultados. Filiais aceitam páginas/tamanho até 200 e busca `q`. Busca avançada/leads aceitam até 50 páginas de 50 resultados. Busca de sócios: 25 páginas de 50. Empresas por cidade: 200 páginas de 100. Resumos em lote: até 10.000 itens, com resultados na mesma ordem.
- **Sessão web:** `/api/exports` e `/api/auth/api-key/*` ainda exigem autenticação de sessão, e não funcionam só com `X-API-Key`. Não são expostos como ferramentas de integração. Exportações privadas, rotação de chave, cobrança, administração e chat interno não fazem parte deste SDK. `panorama_csv` é a exportação de uma publicação pública e está disponível.

## Erros

```python
from cnpjaberto import Client, AuthError, ProRequiredError, RateLimitError

with Client() as cnpj:
    try:
        cnpj.companies_by_contact(email="contato@example.com")
    except ProRequiredError as error:  # 403; subclasse de AuthError
        print("Acesso negado:", error.payload)
    except AuthError as error:        # 401
        print("Verifique a chave:", error.payload)
    except RateLimitError as error:   # 429: throttle ou cota diária/mensal
        print("Aguarde:", error.retry_after, error.payload)
```

`CnpjAbertoError` é a base; `NotFoundError` representa 404 e `QuotaExceededError` representa 402. Todos preservam `status_code`, `payload`, `headers` e `retry_after` quando disponíveis. Outros erros HTTP, JSON inválido e falhas de transporte usam a classe base. Redirecionamentos não são seguidos. Validações locais lançam `ValueError`; validações adicionais do backend preservam o erro 400/422. O MCP reporta falhas como erros de ferramenta, com detalhes da API e `Retry-After` quando presente, em vez de resultados vazios.

## Migração da versão 0.1

Os nove nomes MCP originais foram preservados. Mudanças de contrato necessárias:

- CNPJ completo tem **14 caracteres**, aceita letras ASCII em maiúsculas/minúsculas nas primeiras 12 posições e mantém os dois verificadores numéricos. Máscaras são removidas sem descartar letras. Lookup e filiais não aceitam os prefixos de 8/12 caracteres anunciados pela versão antiga. A validação do dígito verificador fica com a API.
- `lookup` com chave retorna apenas o estabelecimento solicitado. Consulte `filiais` para os demais.
- Busca textual passou de 3 para 4 caracteres.
- Joins por endereço e contato exigem PRO na integração. `companies_by_contact` agora também expõe `exclude` no MCP.
- `filiais` ganhou `q`; panoramas nacional/anual ganharam `sem_mei`.
- `close()` não fecha um transporte HTTP fornecido pelo chamador.

## Desenvolvimento e validação

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[mcp,dev]' hatchling
.venv/bin/ruff check src tests examples
.venv/bin/ruff format --check src tests examples
.venv/bin/pytest
.venv/bin/python -m build --no-isolation
```

Contratos revisados contra o backend do repositório `cnpj`, commit `50b17005c81d4c81f2faebd8f322dc5e93d66405` (2026-10-04), incluindo rotas, serviços de autenticação e gates de plano. Testes usam transporte HTTP simulado e sessões MCP reais em memória/stdio; não requerem conta e não consomem cota. Cobrem todas as ferramentas, serialização, erros, planos, schemas e encerramento. Não substituem uma consulta autenticada de ponta a ponta ao ambiente de produção.

## Fontes de dados

Cadastro empresarial da Receita Federal, complementado pelos conjuntos disponibilizados pelo backend para compliance, dívida ativa, B3/CVM e publicações do panorama. Consulte os metadados da resposta para cobertura e atualização; indicadores não constituem prova de irregularidade.

## Licença

MIT.
