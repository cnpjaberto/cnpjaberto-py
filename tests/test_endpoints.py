"""Wire contracts reviewed against cnpj backend at 50b17005 (2026-10-04)."""

import pytest

CNPJ = "18236120000158"

# Expected paths and response kinds come from the backend route declarations.
CASES = [
    ("lookup", {"cnpj": CNPJ}, f"/api/cnpj/{CNPJ}", {}),
    ("filiais", {"cnpj": CNPJ}, f"/api/cnpj/{CNPJ}/filiais", {}),
    ("search", {"q": "banco"}, "/api/search", {"results": []}),
    ("companies_by_owner", {"name": "Maria Silva"}, "/api/socio/empresas", {}),
    (
        "companies_at_same_address",
        {"cep": "01001000", "logradouro": "Praça da Sé", "numero": "1"},
        "/api/endereco/empresas",
        {},
    ),
    (
        "companies_by_contact",
        {"email": "test@example.test", "exclude": "18236120"},
        "/api/contato/empresas",
        {},
    ),
    ("cnae_stats", {"codigo": "6201501"}, "/api/cnae/6201501/stats", {}),
    ("panorama_overview", {"sem_mei": True}, "/api/panorama/overview", {}),
    ("panorama_year", {"year": 2025, "sem_mei": True}, "/api/panorama/year/2025", {}),
    ("owner_summary", {"nome": "Maria Silva"}, "/api/socio/empresas-resumo", {}),
    (
        "owner_summaries",
        {"items": [{"nome": "Maria Silva"}]},
        "/api/socio/empresas-resumo/batch",
        {"items": []},
    ),
    ("participations", {"cnpj": CNPJ}, f"/api/participacoes/{CNPJ}", {}),
    ("control_tree", {"cnpj": CNPJ}, f"/api/controle/{CNPJ}", {}),
    ("common_owners", {"cnpjs": [CNPJ, "00000000"]}, "/api/socios-comum", {}),
    (
        "advanced_search",
        {"uf": "SP", "mei": False},
        "/api/busca-avancada",
        {"results": []},
    ),
    ("competitors", {"cnpj": CNPJ}, f"/api/concorrentes/{CNPJ}", {"results": []}),
    (
        "person_profile",
        {"nome": "Maria Silva", "cpf": "123456"},
        "/api/pessoa/raio-x",
        {"locked": True, "preview": True},
    ),
    ("search_owners", {"nome": "Maria Silva"}, "/api/socios/busca", {"results": []}),
    ("owner_suggestions", {"q": "Maria"}, "/api/socios/autocomplete", {"results": []}),
    (
        "leads",
        {
            "uf": "SP",
            "municipio_codigo": "7107",
            "data_abertura_min": "2026-01-01",
            "com_email": True,
        },
        "/api/leads",
        {"results": [{"email": "pro@upgrade.com", "contact_gated": True}]},
    ),
    (
        "search_cnaes",
        {"q": "software"},
        "/api/cnaes/search",
        [{"codigo": "6201501", "descricao": "Software"}],
    ),
    ("cnae_catalog", {"secao": "J"}, "/api/cnaes/catalog", {"items": []}),
    (
        "search_municipalities",
        {"q": "São Paulo", "uf": "SP"},
        "/api/municipios/search",
        [{"codigo": "7107", "descricao": "São Paulo"}],
    ),
    ("municipalities", {"uf": "SP"}, "/api/municipios-por-uf", [{"codigo": "7107"}]),
    (
        "companies_by_city",
        {"uf": "SP", "municipio": "7107", "logradouro": "Sé", "bairro": "Centro"},
        "/api/empresas-cidade",
        {},
    ),
    ("service_catalog", {}, "/api/servicos/catalog", {"servicos": []}),
    (
        "search_services",
        {
            "servico": "encanador",
            "uf": "SP",
            "municipio_codigo": "7107",
            "sem_mei": True,
        },
        "/api/servicos",
        {},
    ),
    ("business_group", {"cnpj": CNPJ}, f"/api/intelligence/grupo/{CNPJ}", {}),
    ("red_flags", {"cnpj": CNPJ}, f"/api/intelligence/red-flags/{CNPJ}", {}),
    (
        "ownership_network",
        {"q": "Maria Silva", "cpf": "123456"},
        "/api/intelligence/rede",
        {},
    ),
    ("compliance_summary", {"cnpj": CNPJ}, f"/api/compliance/resumo/{CNPJ}", {}),
    ("compliance_dossier", {"cnpj": CNPJ}, f"/api/compliance/dossie/{CNPJ}", {}),
    (
        "active_debt",
        {"cnpj": CNPJ},
        f"/api/compliance/divida-ativa/{CNPJ}",
        {"encontrado": False},
    ),
    ("panorama_catalog", {"edicao": "2026-09"}, "/api/panorama/catalog", {}),
    (
        "panorama_report",
        {
            "periodo": "2025",
            "uf": "SP",
            "recorte": "todos",
            "tema": "tecnologia",
            "edicao": "2026-09",
        },
        "/api/panorama/report/2025",
        {},
    ),
    (
        "panorama_csv",
        {"periodo": "2025", "tabela": "cnaes"},
        "/api/panorama/report/2025/csv",
        "codigo,total\n6201501,42\n",
    ),
    (
        "panorama_revisions",
        {"periodo": "2025"},
        "/api/panorama/report/2025/revisions",
        {},
    ),
    ("panorama_alphanumeric", {"ano": 2026}, "/api/panorama/alfanumericos/2026", {}),
    ("stock_catalog", {"tipo": "ACAO"}, "/api/bolsa/catalog", {"items": []}),
    ("stock_ticker", {"ticker": "PETR4"}, "/api/bolsa/ticker/PETR4", {}),
    (
        "fund_catalog",
        {"tipo": "FII", "situacao": "all"},
        "/api/fundos/catalog/FII",
        {"items": []},
    ),
    ("fund", {"cnpj": CNPJ}, f"/api/fundos/cnpj/{CNPJ}", {}),
    (
        "funds_by_auditor",
        {"cnpj": CNPJ, "limit": 50},
        f"/api/fundos/cnpj/{CNPJ}/auditor-related",
        {},
    ),
    (
        "similar_funds",
        {"cnpj": CNPJ, "limit": 20},
        f"/api/fundos/cnpj/{CNPJ}/similares",
        {},
    ),
]


@pytest.mark.parametrize("method,kwargs,path,payload", CASES, ids=[c[0] for c in CASES])
def test_endpoint_contract(sdk, httpx_mock, method, kwargs, path, payload):
    if isinstance(payload, str):
        httpx_mock.add_response(
            text=payload, headers={"Content-Type": "text/csv; charset=utf-8"}
        )
    else:
        httpx_mock.add_response(json=payload)
    assert getattr(sdk, method)(**kwargs) == payload
    request = httpx_mock.get_request()
    assert request.url.path == path
    assert request.method == ("POST" if method == "owner_summaries" else "GET")
    # Supplied query values must survive encoding (including booleans and lists).
    for key, value in kwargs.items():
        if method == "owner_summaries" or key == "cnpj" or str(value) in path:
            continue
        wire_key = "nome" if key == "name" else key
        expected = str(value).lower() if isinstance(value, bool) else str(value)
        if isinstance(value, list):
            assert request.url.params.get_list(wire_key) == value
        else:
            assert request.url.params[wire_key] == expected
