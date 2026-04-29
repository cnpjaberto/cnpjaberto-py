from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://cnpjaberto.com.br"
DEFAULT_TIMEOUT = 30.0


class CnpjAbertoError(Exception):
    """Base error for cnpjaberto API failures."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class AuthError(CnpjAbertoError):
    """401/403 — missing or invalid API key."""


class NotFoundError(CnpjAbertoError):
    """404 — CNPJ or resource not found."""


class RateLimitError(CnpjAbertoError):
    """429 — daily quota exceeded or per-IP throttle."""


class Client:
    """Synchronous client for the cnpjaberto.com.br public API.

    API key is read from ``CNPJABERTO_API_KEY`` env var when not passed
    explicitly. Anonymous requests are allowed but subject to the public
    rate limit; pass an API key (Pro plan) for the daily quota tier.
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
        """Full company record. Top-level: ``razao_social``, ``capital_social``,
        ``natureza_juridica*``, ``simples``, ``socios``, ``estabelecimentos`` (list,
        with ``situacao_cadastral``, address, CNAEs)."""
        return self._get(f"/api/cnpj/{_normalize_cnpj(cnpj)}")

    def filiais(
        self,
        cnpj: str,
        *,
        page: int = 1,
        per_page: int = 50,
        uf: str | None = None,
    ) -> dict:
        """Branches (filiais) of a company; optionally filter by UF."""
        return self._get(
            f"/api/cnpj/{_normalize_cnpj(cnpj)}/filiais",
            params={"page": page, "per_page": per_page, "uf": uf},
        )

    def search(self, q: str, *, page: int = 1, per_page: int = 20) -> dict:
        """Search by name, fantasy, or CNPJ digits. ``q`` requires ≥ 3 chars;
        ``per_page`` is capped at 20."""
        if len(q.strip()) < 3:
            raise ValueError("`q` must be at least 3 characters")
        return self._get("/api/search", params={"q": q, "page": page, "per_page": per_page})

    def companies_by_owner(
        self,
        name: str,
        *,
        cpf: str | None = None,
        exclude: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Companies where a person appears as partner. ``cpf`` (digits, partial OK)
        disambiguates homonyms; ``exclude`` removes one ``cnpj_basico`` from results."""
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
        """Companies sharing a specific address (CEP + street + number).
        ``cep`` is exactly 8 digits, no dash."""
        cep_digits = _digits(cep)
        if len(cep_digits) != 8:
            raise ValueError("`cep` must contain exactly 8 digits")
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
        """Companies sharing a contact. Pass either ``email`` OR (``ddd`` AND
        ``telefone``) — phone match needs the area code separately."""
        if not email and not (ddd and telefone):
            raise ValueError("Provide `email` or both `ddd` and `telefone`")
        return self._get(
            "/api/contato/empresas",
            params={
                "email": email, "ddd": ddd, "telefone": telefone,
                "exclude": exclude, "limit": limit,
            },
        )

    def cnae_stats(self, codigo: str) -> dict:
        """Aggregate stats for a CNAE (count of companies, top UFs, etc.)."""
        return self._get(f"/api/cnae/{codigo}/stats")

    def panorama_overview(self) -> dict:
        """National overview: totals, top UFs, top CNAEs, capital ranges, etc."""
        return self._get("/api/panorama/overview")

    def panorama_year(self, year: int) -> dict:
        """Yearly cut: openings, closings, monthly series, top CNAEs/UFs."""
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
