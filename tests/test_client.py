import json

import httpx
import pytest

from cnpjaberto import (
    AuthError,
    Client,
    CnpjAbertoError,
    NotFoundError,
    ProRequiredError,
    QuotaExceededError,
    RateLimitError,
    __version__,
)

CNPJ = "18236120000158"


def test_lookup_preserves_establishment_and_alphanumeric(sdk, httpx_mock):
    payload = {
        "razao_social": "EXEMPLO",
        "estabelecimentos": [{"cnpj": "12ABC34501DE35"}],
    }
    httpx_mock.add_response(json=payload)
    assert sdk.lookup("12.abc.345/01de-35") == payload
    req = httpx_mock.get_request()
    assert req.url.path == "/api/cnpj/12ABC34501DE35"
    assert req.headers["X-API-Key"] == "test-key"
    assert req.headers["User-Agent"] == f"cnpjaberto-py/{__version__}"


@pytest.mark.parametrize(
    "cnpj",
    [
        "",
        "18236120",
        "182361200001",
        "12ABC34501DEAA",
        "１２ABC34501DE35",
        "12ßC34501DE35",
        "18?236120000158",
    ],
)
def test_invalid_cnpj_does_not_make_request(sdk, cnpj):
    with pytest.raises(ValueError):
        sdk.lookup(cnpj)


def test_legacy_parameters_and_new_filial_query(sdk, httpx_mock):
    httpx_mock.add_response(json={"items": []})
    sdk.filiais(CNPJ, page=200, per_page=200, uf="SP", q="centro")
    assert dict(httpx_mock.get_request().url.params) == {
        "page": "200",
        "per_page": "200",
        "uf": "SP",
        "q": "centro",
    }


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("search", {"q": "abc"}),
        ("search", {"q": "abcd", "page": 51}),
        ("search", {"q": "abcd", "per_page": 21}),
        ("filiais", {"cnpj": CNPJ, "page": 201}),
        ("companies_by_owner", {"name": "Maria Silva", "limit": 51}),
        ("companies_by_contact", {}),
        ("companies_by_contact", {"email": "a@b.test", "limit": 101}),
        (
            "companies_at_same_address",
            {"cep": "123", "logradouro": "Rua", "numero": "1"},
        ),
        ("advanced_search", {"uf": "SP", "page": 51}),
        ("search_owners", {}),
        ("search_owners", {"nome": "Maria Silva", "page": 26}),
        ("common_owners", {"cnpjs": [CNPJ, "18236120"]}),
        ("common_owners", {"cnpjs": [CNPJ, "00000000"], "modo": "bad"}),
        ("owner_summaries", {"items": [{"cpf": "123"}]}),
        ("owner_summaries", {"items": [{"nome": "Maria", "other": "bad"}]}),
        ("owner_summaries", {"items": [{"nome": "Maria"}] * 10001}),
        ("fund", {"cnpj": "12ABC34501DE35"}),
    ],
)
def test_invalid_inputs(sdk, method, kwargs):
    with pytest.raises(ValueError):
        getattr(sdk, method)(**kwargs)


def test_advanced_search_sends_all_filters_without_dropping_false_or_zero(
    sdk, httpx_mock
):
    httpx_mock.add_response(json={"results": []})
    sdk.advanced_search(
        uf="SP,RJ",
        cnae="6201501,6202300",
        situacao="02",
        capital_min=0,
        capital_max=500000,
        mei=False,
        porte="ME,EPP",
        municipio="São Paulo",
        municipio_codigo="7107",
        municipio_uf="SP",
        nome_empresa="TESTE",
        com_email=True,
        com_telefone=False,
        email="a+b@example.test",
        telefone="11999999999",
        cep="01001-000",
        numero="0",
        page=2,
        per_page=50,
    )
    params = dict(httpx_mock.get_request().url.params)
    assert params == {
        "uf": "SP,RJ",
        "cnae": "6201501,6202300",
        "situacao": "02",
        "capital_min": "0",
        "capital_max": "500000",
        "mei": "false",
        "porte": "ME,EPP",
        "municipio": "São Paulo",
        "municipio_codigo": "7107",
        "municipio_uf": "SP",
        "nome_empresa": "TESTE",
        "com_email": "true",
        "com_telefone": "false",
        "email": "a+b@example.test",
        "telefone": "11999999999",
        "cep": "01001-000",
        "numero": "0",
        "page": "2",
        "per_page": "50",
    }


def test_repeated_cnpjs(sdk, httpx_mock):
    httpx_mock.add_response(json={"socios": []})
    sdk.common_owners(
        ["18.236.120/0001-58", "12abc345"], modo="sobreposicao", min_empresas=2
    )
    params = httpx_mock.get_request().url.params
    assert params.get_list("cnpjs") == [CNPJ, "12ABC345"]
    assert params["modo"] == "sobreposicao"


def test_batch_body_and_order(sdk, httpx_mock):
    items = [{"nome": "Maria Silva", "cpf": "123456"}, {"nome": "José Silva"}]
    payload = {"items": [{"total": 3}, {"total": 0}]}
    httpx_mock.add_response(json=payload)
    assert sdk.owner_summaries(items, exclude="18236120", limit=10) == payload
    request = httpx_mock.get_request()
    assert request.method == "POST"
    assert request.url.path == "/api/socio/empresas-resumo/batch"
    assert json.loads(request.content) == {
        "items": items,
        "exclude": "18236120",
        "limit": 10,
    }


def test_contact_exclude_and_cep_normalization(sdk, httpx_mock):
    httpx_mock.add_response(json={})
    httpx_mock.add_response(json={})
    sdk.companies_by_contact(
        ddd="11", telefone="12345678", exclude="18236120", limit=100
    )
    sdk.companies_at_same_address("01001-000", "Praça da Sé", "1", exclude="18236120")
    requests = httpx_mock.get_requests()
    assert dict(requests[0].url.params) == {
        "ddd": "11",
        "telefone": "12345678",
        "exclude": "18236120",
        "limit": "100",
    }
    assert requests[1].url.params["cep"] == "01001000"


@pytest.mark.parametrize(
    "status,error",
    [
        (401, AuthError),
        (402, QuotaExceededError),
        (403, ProRequiredError),
        (404, NotFoundError),
        (429, RateLimitError),
        (422, CnpjAbertoError),
        (503, CnpjAbertoError),
    ],
)
def test_errors_keep_server_detail_and_retry_after(sdk, httpx_mock, status, error):
    payload = {"detail": {"error": "Plano Pro necessário", "upgrade_url": "/planos"}}
    httpx_mock.add_response(
        status_code=status, json=payload, headers={"Retry-After": "3"}
    )
    with pytest.raises(error) as caught:
        sdk.lookup(CNPJ)
    exc = caught.value
    assert exc.status_code == status
    assert exc.payload == payload
    assert exc.retry_after == "3"
    assert "Plano Pro necessário" in str(exc)
    assert len(httpx_mock.get_requests()) == 1  # no automatic quota-consuming retries


def test_pro_error_remains_backwards_compatible():
    assert issubclass(ProRequiredError, AuthError)


def test_transport_error_does_not_expose_key(sdk, httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("test-key sensitive"))
    with pytest.raises(CnpjAbertoError, match="HTTP transport error") as caught:
        sdk.lookup(CNPJ)
    assert "test-key" not in str(caught.value)


def test_non_json_and_redirects(sdk, httpx_mock):
    httpx_mock.add_response(text="<html>Unavailable</html>", status_code=503)
    httpx_mock.add_response(text="not json")
    httpx_mock.add_response(
        status_code=302, headers={"Location": "https://other.test/"}
    )
    for expected in ("HTTP 503", "invalid JSON", "HTTP 302"):
        with pytest.raises(CnpjAbertoError, match=expected):
            sdk.lookup(CNPJ)
    assert len(httpx_mock.get_requests()) == 3


def test_borrowed_client_auth_base_url_and_lifetime():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={})

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://wrong.test",
        auth=("user", "password"),
        headers={"Authorization": "Bearer old"},
    ) as http:
        with Client("right-key", client=http, base_url="https://right.test/") as sdk:
            sdk.lookup(CNPJ)
        assert not http.is_closed
    assert seen[0].url.host == "right.test"
    assert seen[0].headers["X-API-Key"] == "right-key"
    assert "Authorization" not in seen[0].headers


def test_owned_client_and_environment(monkeypatch):
    monkeypatch.setenv("CNPJABERTO_API_KEY", "from-env")
    with Client() as sdk:
        assert sdk.api_key == "from-env"
        http = sdk._http
    assert http.is_closed
