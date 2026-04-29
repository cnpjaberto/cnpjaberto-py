from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://cnpjaberto.com.br"
DEFAULT_TIMEOUT = 30.0


class CnpjAbertoError(Exception):
    """Erro base para falhas da API cnpjaberto."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class AuthError(CnpjAbertoError):
    """401 ou 403, chave de API ausente ou inválida."""


class NotFoundError(CnpjAbertoError):
    """404, CNPJ ou recurso não encontrado."""


class RateLimitError(CnpjAbertoError):
    """429, cota diária excedida ou throttle por IP."""


class Client:
    """Cliente síncrono da API pública do cnpjaberto.com.br.

    Quando não passada explicitamente, a chave é lida da variável de ambiente
    ``CNPJABERTO_API_KEY``. Requisições anônimas funcionam, sujeitas ao rate
    limit público. Para a cota diária do plano Pro, passe a chave de API.
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
        headers = {"User-Agent": "cnpjaberto-py/0.1.0"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
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
        self._http.close()

    # ── HTTP plumbing ────────────────────────────────────────────────

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            r = self._http.get(path, params=clean_params)
        except httpx.HTTPError as e:
            raise CnpjAbertoError(f"HTTP transport error: {e}") from e
        return self._handle(r)

    @staticmethod
    def _handle(r: httpx.Response) -> Any:
        if r.status_code == 401 or r.status_code == 403:
            raise AuthError(
                f"Authentication failed ({r.status_code})",
                status_code=r.status_code,
                payload=_safe_json(r),
            )
        if r.status_code == 404:
            raise NotFoundError("Resource not found", status_code=404, payload=_safe_json(r))
        if r.status_code == 429:
            raise RateLimitError("Rate limit exceeded", status_code=429, payload=_safe_json(r))
        if r.status_code >= 400:
            raise CnpjAbertoError(
                f"HTTP {r.status_code}: {r.text[:200]}",
                status_code=r.status_code,
                payload=_safe_json(r),
            )
        return r.json()

    # ── Tools ────────────────────────────────────────────────────────

    def lookup(self, cnpj: str) -> dict:
        """Registro completo da empresa. Campos no topo: ``razao_social``,
        ``capital_social``, ``natureza_juridica*``, ``simples``, ``socios``,
        ``estabelecimentos`` (lista com ``situacao_cadastral``, endereço, CNAEs)."""
        return self._get(f"/api/cnpj/{_normalize_cnpj(cnpj)}")

    def filiais(
        self,
        cnpj: str,
        *,
        page: int = 1,
        per_page: int = 50,
        uf: str | None = None,
    ) -> dict:
        """Filiais de uma matriz, opcionalmente filtradas por UF."""
        return self._get(
            f"/api/cnpj/{_normalize_cnpj(cnpj)}/filiais",
            params={"page": page, "per_page": per_page, "uf": uf},
        )

    def search(self, q: str, *, page: int = 1, per_page: int = 20) -> dict:
        """Busca por razão social, fantasia ou dígitos do CNPJ. ``q`` exige no
        mínimo 3 caracteres; ``per_page`` é limitado a 20."""
        if len(q.strip()) < 3:
            raise ValueError("`q` precisa ter pelo menos 3 caracteres")
        return self._get("/api/search", params={"q": q, "page": page, "per_page": per_page})

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
        """Empresas registradas no mesmo endereço (CEP, logradouro, número).
        ``cep`` precisa ter exatamente 8 dígitos, sem traço."""
        cep_digits = _digits(cep)
        if len(cep_digits) != 8:
            raise ValueError("`cep` precisa ter exatamente 8 dígitos")
        return self._get(
            "/api/endereco/empresas",
            params={
                "cep": cep_digits, "logradouro": logradouro, "numero": numero,
                "exclude": exclude, "limit": limit,
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
        """Empresas que compartilham um contato. Informe ``email`` OU
        (``ddd`` E ``telefone``); a busca por telefone exige o DDD separado."""
        if not email and not (ddd and telefone):
            raise ValueError("Informe `email` ou ambos `ddd` e `telefone`")
        return self._get(
            "/api/contato/empresas",
            params={
                "email": email, "ddd": ddd, "telefone": telefone,
                "exclude": exclude, "limit": limit,
            },
        )

    def cnae_stats(self, codigo: str) -> dict:
        """Estatísticas agregadas de um CNAE (contagem, top UFs, etc.)."""
        return self._get(f"/api/cnae/{codigo}/stats")

    def panorama_overview(self) -> dict:
        """Panorama nacional: totais, top UFs, top CNAEs, faixas de capital."""
        return self._get("/api/panorama/overview")

    def panorama_year(self, year: int) -> dict:
        """Recorte anual: aberturas, fechamentos, série mensal, top CNAEs e UFs."""
        return self._get(f"/api/panorama/year/{int(year)}")


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return r.text


def _normalize_cnpj(cnpj: str) -> str:
    return _digits(cnpj)


def _digits(s: str) -> str:
    return "".join(ch for ch in str(s) if ch.isdigit())
