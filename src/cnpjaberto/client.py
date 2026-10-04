from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

import httpx

from cnpjaberto._version import __version__

DEFAULT_BASE_URL = "https://cnpjaberto.com.br"
DEFAULT_TIMEOUT = 30.0


class CnpjAbertoError(Exception):
    """Erro base para falhas da API cnpjaberto."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: Any = None,
        headers: httpx.Headers | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.headers = httpx.Headers(headers)
        self.retry_after = self.headers.get("Retry-After")


class AuthError(CnpjAbertoError):
    """401 ou 403: autenticação inválida ou acesso negado."""


class ProRequiredError(AuthError):
    """403: acesso negado, incluindo recursos exclusivos do Pro."""


class QuotaExceededError(CnpjAbertoError):
    """402: cota paga esgotada."""


class NotFoundError(CnpjAbertoError):
    """404, CNPJ ou recurso não encontrado."""


class RateLimitError(CnpjAbertoError):
    """429: cota diária/mensal excedida ou throttle."""


class Client:
    """Cliente síncrono da API do cnpjaberto.com.br.

    A chave de API é obrigatória. Quando não passada explicitamente, é lida
    da variável de ambiente ``CNPJABERTO_API_KEY``. Crie uma conta gratuita
    em cnpjaberto.com.br/planos para gerar a sua.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("CNPJABERTO_API_KEY")
        self.base_url = base_url.rstrip("/")
        headers = {"User-Agent": f"cnpjaberto-py/{__version__}"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        self._headers = headers
        self._owns_client = client is None
        self._http = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=headers,
        )

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    # ── HTTP plumbing ────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        text: bool = False,
    ) -> Any:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            request = self._http.build_request(
                method,
                self.base_url + path,
                params=clean_params,
                json=json,
                headers=self._headers,
            )
            # A borrowed transport must not introduce mixed authentication.
            request.headers.pop("Authorization", None)
            response = self._http.send(request, follow_redirects=False, auth=None)
        except httpx.HTTPError as e:
            raise CnpjAbertoError("HTTP transport error") from e
        return self._handle(response, text=text)

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    @staticmethod
    def _handle(r: httpx.Response, *, text: bool = False) -> Any:
        if r.status_code >= 300:
            payload = _safe_json(r)
            detail = (
                payload.get("detail", payload) if isinstance(payload, dict) else None
            )
            message = f"HTTP {r.status_code}"
            if detail is not None:
                message += f": {detail}"
            error = {
                401: AuthError,
                402: QuotaExceededError,
                403: ProRequiredError,
                404: NotFoundError,
                429: RateLimitError,
            }.get(r.status_code, CnpjAbertoError)
            raise error(
                message, status_code=r.status_code, payload=payload, headers=r.headers
            )
        if text:
            return r.text
        if r.status_code == 204:
            return None
        try:
            return r.json()
        except ValueError as e:
            raise CnpjAbertoError(
                "API returned invalid JSON", status_code=r.status_code
            ) from e

    # ── Tools ────────────────────────────────────────────────────────

    def lookup(self, cnpj: str) -> dict:
        """Consulta CNPJ completo (14 caracteres, numérico ou alfanumérico).
        Com API key, estabelecimentos contém apenas o estabelecimento solicitado.
        Use filiais para paginar os demais. Sócios e demais campos são preservados.
        """
        return self._get(f"/api/cnpj/{_normalize_cnpj(cnpj)}")

    def filiais(
        self,
        cnpj: str,
        *,
        page: int = 1,
        per_page: int = 50,
        uf: str | None = None,
        q: str | None = None,
    ) -> dict:
        """Filiais por CNPJ completo; filtro UF e busca textual q. Página/tamanho: 1–200."""
        _range("page", page, 1, 200)
        _range("per_page", per_page, 1, 200)
        return self._get(
            f"/api/cnpj/{_normalize_cnpj(cnpj)}/filiais",
            params={"page": page, "per_page": per_page, "uf": uf, "q": q},
        )

    def search(self, q: str, *, page: int = 1, per_page: int = 20) -> dict:
        """Busca por razão social, fantasia ou dígitos do CNPJ. ``q`` exige no
        mínimo 4 caracteres; ``per_page`` é limitado a 20."""
        if len(q.strip()) < 4:
            raise ValueError("`q` precisa ter pelo menos 4 caracteres")
        _range("page", page, 1, 50)
        _range("per_page", per_page, 1, 20)
        return self._get(
            "/api/search", params={"q": q, "page": page, "per_page": per_page}
        )

    def companies_by_owner(
        self,
        name: str,
        *,
        cpf: str | None = None,
        exclude: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Empresas onde a pessoa aparece como sócia. ``cpf`` em dígitos
        (parcial é aceito) ajuda a desambiguar homônimos; ``exclude`` remove
        um ``cnpj_basico`` específico do resultado."""
        _range("limit", limit, 1, 50)
        return self._get(
            "/api/socio/empresas",
            params={"nome": name, "cpf": cpf, "exclude": exclude, "limit": limit},
        )

    def companies_at_same_address(
        self,
        cep: str,
        logradouro: str,
        numero: str,
        *,
        exclude: str | None = None,
        limit: int = 20,
    ) -> dict:
        """PRO: empresas registradas no mesmo endereço (CEP, logradouro, número).
        ``cep`` precisa ter exatamente 8 dígitos, sem traço."""
        _range("limit", limit, 1, 100)
        cep_digits = _digits(cep)
        if len(cep_digits) != 8:
            raise ValueError("`cep` precisa ter exatamente 8 dígitos")
        return self._get(
            "/api/endereco/empresas",
            params={
                "cep": cep_digits,
                "logradouro": logradouro,
                "numero": numero,
                "exclude": exclude,
                "limit": limit,
            },
        )

    def companies_by_contact(
        self,
        *,
        email: str | None = None,
        ddd: str | None = None,
        telefone: str | None = None,
        exclude: str | None = None,
        limit: int = 20,
    ) -> dict:
        """PRO: empresas que compartilham um contato. Informe ``email`` OU
        (``ddd`` E ``telefone``); a busca por telefone exige o DDD separado."""
        _range("limit", limit, 1, 100)
        if not email and not (ddd and telefone):
            raise ValueError("Informe `email` ou ambos `ddd` e `telefone`")
        return self._get(
            "/api/contato/empresas",
            params={
                "email": email,
                "ddd": ddd,
                "telefone": telefone,
                "exclude": exclude,
                "limit": limit,
            },
        )

    def cnae_stats(self, codigo: str) -> dict:
        """Estatísticas agregadas de um CNAE (contagem, top UFs, etc.)."""
        return self._get(f"/api/cnae/{_segment(codigo)}/stats")

    def panorama_overview(self, *, sem_mei: bool = False) -> dict:
        """Panorama nacional: totais, top UFs, top CNAEs, faixas de capital."""
        return self._get("/api/panorama/overview", params={"sem_mei": sem_mei})

    def panorama_year(self, year: int, *, sem_mei: bool = False) -> dict:
        """Recorte anual: aberturas, fechamentos, série mensal, top CNAEs e UFs."""
        return self._get(f"/api/panorama/year/{int(year)}", params={"sem_mei": sem_mei})

    def owner_summary(
        self,
        nome: str,
        *,
        exclude: str | None = None,
        cpf: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Resumo das empresas de um sócio; CPF parcial ajuda a desambiguar homônimos.

        nome: Nome do sócio
        exclude: CNPJ básico a excluir
        cpf: Dígitos do CPF/CNPJ do sócio (parcial); reduz homônimos no mesmo nome
        """
        _range("limit", limit, 1, 50)
        return self._get(
            "/api/socio/empresas-resumo",
            params={"nome": nome, "exclude": exclude, "cpf": cpf, "limit": limit},
        )

    def participations(self, cnpj: str, *, limit: int = 20) -> dict[str, Any]:
        """PRO: empresas que têm este CNPJ como sócio pessoa jurídica."""
        _range("limit", limit, 1, 100)
        return self._get(
            f"/api/participacoes/{_normalize_cnpj(cnpj)}", params={"limit": limit}
        )

    def cnae_catalog(self, *, secao: str | None = None) -> dict[str, Any]:
        """Catálogo CNAE; secao opcional A–U. Sem seção, retorna todo o catálogo.

        secao: Letra da seção (A–U). Quando informado, retorna só CNAEs dessa seção.
        """
        return self._get("/api/cnaes/catalog", params={"secao": secao})

    def control_tree(self, cnpj: str) -> dict[str, Any]:
        """PRO: árvore de controle societário da empresa."""
        return self._get(f"/api/controle/{_normalize_cnpj(cnpj)}", params={})

    def common_owners(
        self, cnpjs: list[str], *, modo: str = "intersecao", min_empresas: int = 2
    ) -> dict[str, Any]:
        """PRO: cruza sócios de 2 ou mais raízes distintas. modo: intersecao ou sobreposicao; min_empresas: 2–50.

        cnpjs: CNPJs (≥8 dígitos); repita o parâmetro ou separe por vírgula em um valor
        modo: intersecao: sócios em todas; sobreposicao: sócios em ≥ min_empresas
        """
        _range("min_empresas", min_empresas, 2, 50)
        cnpjs = [_normalize_cnpj_prefix(c) for c in cnpjs]
        if len({c[:8] for c in cnpjs}) < 2:
            raise ValueError("Informe pelo menos duas raízes CNPJ distintas")
        if modo not in {"intersecao", "sobreposicao"}:
            raise ValueError("modo deve ser intersecao ou sobreposicao")
        return self._get(
            "/api/socios-comum",
            params={"cnpjs": cnpjs, "modo": modo, "min_empresas": min_empresas},
        )

    def advanced_search(
        self,
        *,
        uf: str | None = None,
        cnae: str | None = None,
        situacao: str | None = None,
        capital_min: float | None = None,
        capital_max: float | None = None,
        mei: bool | None = None,
        porte: str | None = None,
        municipio: str | None = None,
        municipio_codigo: str | None = None,
        municipio_uf: str | None = None,
        nome_empresa: str | None = None,
        com_email: bool = False,
        com_telefone: bool = False,
        email: str | None = None,
        telefone: str | None = None,
        cep: str | None = None,
        numero: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """Busca por filtros combinados. Informe pelo menos um filtro seletivo. UF aceita até 5 estados separados por vírgula; CNAE, situação e porte também aceitam vírgulas. Contato/endereço exato e filtros com_email/com_telefone exigem PRO. Prefira municipio_codigo e municipio_uf ao nome parcial.

        uf: UF (até 5, separadas por vírgula; vazio = Brasil inteiro)
        cnae: Código CNAE (comma-separated para múltiplos)
        situacao: Situação cadastral (comma-separated)
        capital_min: Capital social mínimo
        capital_max: Capital social máximo
        mei: Filtrar MEI (true/false)
        porte: Porte (comma-separated: ME, EPP, Demais)
        municipio: (Legado) Nome da cidade (busca parcial). Prefira `municipio_codigo`.
        municipio_codigo: Código IBGE do município (4-7 dígitos). Quando presente, usado para filtro exato e ignora `municipio`.
        municipio_uf: UF do município (2 letras). Desambigua código quando há vários estados selecionados.
        nome_empresa: Prefixo da razão social ou nome fantasia. Mínimo 4 caracteres.
        com_email: Apenas empresas com e-mail (exclusivo Pro)
        com_telefone: Apenas empresas com telefone (exclusivo Pro)
        email: Busca pelo e-mail exato publicado na RF (exclusivo Pro).
        telefone: Busca pelo telefone publicado na RF (exclusivo Pro). DDD é opcional — sem ele o número casa em qualquer DDD. Aceita máscara e DDI 55; o nono dígito de celular é ignorado, porque a RF grava o formato legado de 8 dígitos.
        cep: CEP exato (8 dígitos, com ou sem máscara) do estabelecimento (exclusivo Pro). É o filtro que reproduz o card "empresas neste endereço" da ficha.
        numero: Número do logradouro, refinando `cep` (exclusivo Pro). Ignorado sem `cep` — sozinho não é seletivo.
        """
        _range("page", page, 1, 50)
        _range("per_page", per_page, 1, 50)
        return self._get(
            "/api/busca-avancada",
            params={
                "uf": uf,
                "cnae": cnae,
                "situacao": situacao,
                "capital_min": capital_min,
                "capital_max": capital_max,
                "mei": mei,
                "porte": porte,
                "municipio": municipio,
                "municipio_codigo": municipio_codigo,
                "municipio_uf": municipio_uf,
                "nome_empresa": nome_empresa,
                "com_email": com_email,
                "com_telefone": com_telefone,
                "email": email,
                "telefone": telefone,
                "cep": cep,
                "numero": numero,
                "page": page,
                "per_page": per_page,
            },
        )

    def competitors(self, cnpj: str) -> dict[str, Any]:
        """Até 8 concorrentes da empresa; o backend não aceita parâmetro limit."""
        return self._get(f"/api/concorrentes/{_normalize_cnpj(cnpj)}", params={})

    def person_profile(self, nome: str, *, cpf: str | None = None) -> dict[str, Any]:
        """Raio-X da pessoa por nome e CPF parcial. Free retorna prévia; PRO retorna análise completa. Preserve os indicadores de bloqueio da resposta.

        nome: Nome completo da pessoa
        cpf: CPF (completo ou trecho). CPF de 11 dígitos: usados só os 6 centrais públicos na Receita.
        """
        return self._get("/api/pessoa/raio-x", params={"nome": nome, "cpf": cpf})

    def search_owners(
        self,
        *,
        nome: str | None = None,
        cpf: str | None = None,
        faixa_etaria: str | None = None,
        municipio: str | None = None,
        municipio_codigo: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """Busca sócios por nome ou CPF/CNPJ. Exige nome ou documento; refine nomes amplos com sobrenome ou cidade. faixa_etaria aceita códigos 1–9 separados por vírgula.

        nome: Nome do sócio (busca parcial)
        cpf: Dígitos do CPF/CNPJ
        faixa_etaria: Faixa etária (comma-separated, códigos 1-9)
        municipio: (Legado) Nome da cidade do estabelecimento matriz. Prefira `municipio_codigo`.
        municipio_codigo: Código IBGE do município (matriz). Filtro exato.
        """
        _range("page", page, 1, 25)
        _range("per_page", per_page, 1, 50)
        if not nome and not cpf:
            raise ValueError("Informe nome ou CPF/CNPJ")
        return self._get(
            "/api/socios/busca",
            params={
                "nome": nome,
                "cpf": cpf,
                "faixa_etaria": faixa_etaria,
                "municipio": municipio,
                "municipio_codigo": municipio_codigo,
                "page": page,
                "per_page": per_page,
            },
        )

    def owner_suggestions(self, q: str, *, limit: int = 10) -> dict[str, Any]:
        """Sugestões de sócios e MEI/EI por nome (mínimo 3 caracteres).

        q: Nome do sócio (mín. 3 chars)
        """
        _range("limit", limit, 1, 15)
        return self._get("/api/socios/autocomplete", params={"q": q, "limit": limit})

    def leads(
        self,
        uf: str,
        municipio_codigo: str,
        *,
        cnae: str | None = None,
        situacao: str | None = None,
        capital_min: float | None = None,
        capital_max: float | None = None,
        idade_min: int | None = None,
        idade_max: int | None = None,
        data_abertura_min: str | None = None,
        data_abertura_max: str | None = None,
        com_email: bool = False,
        com_telefone: bool = False,
        porte: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """Prospecção por UF e município obrigatórios. Resolva municipio_codigo com search_municipalities. Free mascara contatos (contact_gated); PRO libera contato. Não trate valores mascarados como contatos reais. Datas de abertura em YYYY-MM-DD.

        uf: UF (obrigatório, 2 letras)
        municipio_codigo: Código do município (4-7 dígitos, ex.: '7107' para São Paulo/SP). Obrigatório.
        cnae: CNAE (comma-separated para múltiplos)
        situacao: Situação cadastral
        capital_min: Capital mínimo
        capital_max: Capital máximo
        idade_min: Idade mínima da empresa (anos)
        idade_max: Idade máxima da empresa (anos)
        data_abertura_min: Data de abertura mínima (ISO YYYY-MM-DD; aberta a partir de)
        data_abertura_max: Data de abertura máxima (ISO YYYY-MM-DD; aberta até)
        com_email: Apenas com email
        com_telefone: Apenas com telefone
        porte: Porte (ME, EPP, Demais; vírgula para múltiplos)
        """
        _range("page", page, 1, 50)
        _range("per_page", per_page, 1, 50)
        return self._get(
            "/api/leads",
            params={
                "uf": uf,
                "municipio_codigo": municipio_codigo,
                "cnae": cnae,
                "situacao": situacao,
                "capital_min": capital_min,
                "capital_max": capital_max,
                "idade_min": idade_min,
                "idade_max": idade_max,
                "data_abertura_min": data_abertura_min,
                "data_abertura_max": data_abertura_max,
                "com_email": com_email,
                "com_telefone": com_telefone,
                "porte": porte,
                "page": page,
                "per_page": per_page,
            },
        )

    def search_cnaes(self, q: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Busca código ou descrição CNAE; retorna lista de código e descrição.

        q: Código ou descrição do CNAE
        """
        _range("limit", limit, 1, 30)
        return self._get("/api/cnaes/search", params={"q": q, "limit": limit})

    def search_municipalities(
        self, q: str, *, uf: str | None = None, limit: int = 15
    ) -> list[dict[str, Any]]:
        """Busca nome de município, opcionalmente por UF. Retorna códigos para leads e advanced_search.

        q: Nome da cidade
        uf: Filtrar por UF
        """
        _range("limit", limit, 1, 30)
        return self._get(
            "/api/municipios/search", params={"q": q, "uf": uf, "limit": limit}
        )

    def municipalities(self, uf: str) -> list[dict[str, Any]]:
        """Municípios de uma UF com códigos e descrições; retorna lista.

        uf: Sigla do estado
        """
        return self._get("/api/municipios-por-uf", params={"uf": uf})

    def companies_by_city(
        self,
        uf: str,
        municipio: str,
        *,
        page: int = 1,
        per_page: int = 50,
        q: str | None = None,
        logradouro: str | None = None,
        bairro: str | None = None,
    ) -> dict[str, Any]:
        """PRO: empresas do município (código), com busca por nome, logradouro e bairro.

        uf: Sigla do estado
        municipio: Código do município
        q: Busca por razão social ou nome fantasia
        logradouro: Nome da via (logradouro); opcionalmente combine com bairro se a rua se repetir
        bairro: Bairro (opcional; refina o filtro de logradouro)
        """
        _range("page", page, 1, 200)
        _range("per_page", per_page, 1, 100)
        return self._get(
            "/api/empresas-cidade",
            params={
                "uf": uf,
                "municipio": municipio,
                "page": page,
                "per_page": per_page,
                "q": q,
                "logradouro": logradouro,
                "bairro": bairro,
            },
        )

    def service_catalog(self) -> dict[str, Any]:
        """Catálogo de serviços com slugs para search_services."""
        return self._get("/api/servicos/catalog", params={})

    def search_services(
        self,
        servico: str,
        uf: str,
        municipio_codigo: str,
        *,
        page: int = 1,
        per_page: int = 20,
        sem_mei: bool = False,
    ) -> dict[str, Any]:
        """Empresas por slug de serviço, UF e código de município. sem_mei exclui MEIs.

        servico: Slug do serviço (ex.: encanador)
        uf: UF
        municipio_codigo: Código IBGE
        sem_mei: Excluir microempreendedores individuais (MEIs)
        """
        _range("page", page, 1, 50)
        _range("per_page", per_page, 1, 50)
        return self._get(
            "/api/servicos",
            params={
                "servico": servico,
                "uf": uf,
                "municipio_codigo": municipio_codigo,
                "page": page,
                "per_page": per_page,
                "sem_mei": sem_mei,
            },
        )

    def business_group(self, cnpj: str) -> dict[str, Any]:
        """PRO: mapa do grupo empresarial por vínculos societários. Mapas amplos podem retornar 503."""
        return self._get(f"/api/intelligence/grupo/{_normalize_cnpj(cnpj)}", params={})

    def red_flags(self, cnpj: str) -> dict[str, Any]:
        """Indicadores cadastrais de atenção da empresa. São sinais para análise, não prova de irregularidade."""
        return self._get(
            f"/api/intelligence/red-flags/{_normalize_cnpj(cnpj)}", params={}
        )

    def ownership_network(self, q: str, *, cpf: str | None = None) -> dict[str, Any]:
        """Rede societária por nome ou CPF. Use cpf parcial para reduzir homônimos; refine buscas amplas.

        q: Nome do sócio ou CPF
        cpf: Dígitos do CPF/CNPJ do sócio (parcial); reduz homônimos no grafo
        """
        return self._get("/api/intelligence/rede", params={"q": q, "cpf": cpf})

    def compliance_summary(self, cnpj: str) -> dict[str, Any]:
        """Resumo de sanções diretas e dívida ativa da própria pessoa jurídica; sem PEP de sócios."""
        return self._get(f"/api/compliance/resumo/{_normalize_cnpj(cnpj)}", params={})

    def compliance_dossier(self, cnpj: str) -> dict[str, Any]:
        """PRO: dossiê de sanções públicas, PEP dos sócios e indicadores de atenção."""
        return self._get(f"/api/compliance/dossie/{_normalize_cnpj(cnpj)}", params={})

    def active_debt(self, cnpj: str) -> dict[str, Any]:
        """Dívida ativa PGFN. encontrado=false é resultado válido, não erro 404."""
        return self._get(
            f"/api/compliance/divida-ativa/{_normalize_cnpj(cnpj)}", params={}
        )

    def panorama_catalog(self, *, edicao: str | None = None) -> dict[str, Any]:
        """Catálogo de períodos e edições publicados; use antes de solicitar relatórios."""
        return self._get("/api/panorama/catalog", params={"edicao": edicao})

    def panorama_report(
        self,
        periodo: str,
        *,
        uf: str = "BR",
        recorte: str = "todos",
        tema: str | None = None,
        edicao: str | None = None,
    ) -> dict[str, Any]:
        """Relatório publicado por período, UF (BR por padrão), recorte, tema e edição. Consulte panorama_catalog para valores disponíveis."""
        return self._get(
            f"/api/panorama/report/{_segment(periodo)}",
            params={"uf": uf, "recorte": recorte, "tema": tema, "edicao": edicao},
        )

    def panorama_csv(
        self,
        periodo: str,
        *,
        tabela: str = "cnaes",
        uf: str = "BR",
        recorte: str = "todos",
        tema: str | None = None,
        edicao: str | None = None,
    ) -> str:
        """CSV do relatório publicado; retorna texto, não JSON. tabela padrão cnaes. Consulte panorama_catalog para períodos e recortes disponíveis."""
        return self._request(
            "GET",
            f"/api/panorama/report/{_segment(periodo)}/csv",
            params={
                "tabela": tabela,
                "uf": uf,
                "recorte": recorte,
                "tema": tema,
                "edicao": edicao,
            },
            text=True,
        )

    def panorama_revisions(self, periodo: str) -> dict[str, Any]:
        """Revisões publicadas de um período do panorama."""
        return self._get(
            f"/api/panorama/report/{_segment(periodo)}/revisions", params={}
        )

    def panorama_alphanumeric(self, ano: int) -> dict[str, Any]:
        """Painel de CNPJs alfanuméricos: totais e série mensal do ano solicitado."""
        return self._get(f"/api/panorama/alfanumericos/{int(ano)}", params={})

    def stock_catalog(self, *, tipo: str | None = None) -> dict[str, Any]:
        """Catálogo B3; tipo opcional ACAO, FII, BDR, UNT ou ETF.

        tipo: Filtrar por tipo_valor: ACAO, FII, BDR, UNT, ETF
        """
        return self._get("/api/bolsa/catalog", params={"tipo": tipo})

    def stock_ticker(self, ticker: str) -> dict[str, Any]:
        """Detalhe de ticker B3, incluindo fundo para FII e tickers relacionados."""
        return self._get(f"/api/bolsa/ticker/{_segment(ticker)}", params={})

    def fund_catalog(
        self, tipo: str, *, situacao: str = "Em Funcionamento Normal"
    ) -> dict[str, Any]:
        """Catálogo CVM: FII, FIF, FIDC, FIP, FIAGRO ou FIIM. situacao=all inclui fundos inativos.

        situacao: Padrão: apenas ativos
        """
        return self._get(
            f"/api/fundos/catalog/{_segment(tipo)}", params={"situacao": situacao}
        )

    def fund(self, cnpj: str) -> dict[str, Any]:
        """Detalhe de fundo CVM por CNPJ numérico completo."""
        return self._get(f"/api/fundos/cnpj/{_numeric_cnpj(cnpj)}", params={})

    def funds_by_auditor(self, cnpj: str, *, limit: int = 20) -> dict[str, Any]:
        """Outros fundos ativos auditados pela mesma firma, ordenados por patrimônio.

        limit: Quantos fundos retornar (top por patrimônio)
        """
        _range("limit", limit, 1, 50)
        return self._get(
            f"/api/fundos/cnpj/{_numeric_cnpj(cnpj)}/auditor-related",
            params={"limit": limit},
        )

    def similar_funds(self, cnpj: str, *, limit: int = 5) -> dict[str, Any]:
        """Fundos similares por categoria e patrimônio líquido."""
        _range("limit", limit, 1, 20)
        return self._get(
            f"/api/fundos/cnpj/{_numeric_cnpj(cnpj)}/similares", params={"limit": limit}
        )

    def owner_summaries(
        self,
        items: list[dict[str, str | None]],
        *,
        exclude: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Resumo em lote de até 10.000 sócios (nome e cpf opcional).
        A ordem dos resultados corresponde à ordem de items. Consulta sem escrita.
        """
        if len(items) > 10_000:
            raise ValueError("Máximo 10.000 sócios por requisição")
        for item in items:
            if not isinstance(item.get("nome"), str) or not item["nome"].strip():
                raise ValueError("Cada sócio deve informar nome")
            if set(item) - {"nome", "cpf"}:
                raise ValueError("Campos aceitos por sócio: nome, cpf")
        _range("limit", limit, 1, 50)
        return self._request(
            "POST",
            "/api/socio/empresas-resumo/batch",
            json={"items": items, "exclude": exclude, "limit": limit},
        )


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except ValueError:
        return r.text


def _normalize_cnpj(cnpj: str) -> str:
    value = re.sub(r"[.\s/\-]", "", str(cnpj))
    if not value.isascii():
        raise ValueError("CNPJ deve conter apenas caracteres ASCII")
    value = value.upper()
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", value):
        raise ValueError(
            "CNPJ deve ter 14 caracteres ASCII; os dois últimos são dígitos"
        )
    return value


def _digits(s: str) -> str:
    return "".join(ch for ch in str(s) if ch in "0123456789")


def _range(name: str, value: int, minimum: int, maximum: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{name} deve estar entre {minimum} e {maximum}")


def _segment(value: str) -> str:
    if not value or value in {".", ".."}:
        raise ValueError("Parâmetro de caminho vazio ou inválido")
    return quote(value, safe="")


def _normalize_cnpj_prefix(cnpj: str) -> str:
    value = re.sub(r"[.\s/\-]", "", str(cnpj))
    if not value.isascii():
        raise ValueError("CNPJ deve conter apenas caracteres ASCII")
    value = value.upper()
    if not re.fullmatch(r"[0-9A-Z]{8}|[0-9A-Z]{12}|[0-9A-Z]{12}[0-9]{2}", value):
        raise ValueError("Informe CNPJ completo ou prefixo de 8 ou 12 caracteres")
    return value


def _numeric_cnpj(cnpj: str) -> str:
    value = _normalize_cnpj(cnpj)
    if not value.isdigit():
        raise ValueError("O catálogo CVM aceita apenas CNPJ numérico")
    return value
