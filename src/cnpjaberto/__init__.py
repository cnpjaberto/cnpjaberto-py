from cnpjaberto.client import (
    AuthError,
    Client,
    CnpjAbertoError,
    NotFoundError,
    ProRequiredError,
    QuotaExceededError,
    RateLimitError,
)

__all__ = [
    "__version__",
    "Client",
    "CnpjAbertoError",
    "NotFoundError",
    "RateLimitError",
    "AuthError",
    "ProRequiredError",
    "QuotaExceededError",
]

from cnpjaberto._version import __version__
