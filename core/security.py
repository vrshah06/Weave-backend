import hmac
from typing import Optional

from fastapi import Header, Query

from core.config import config
from core.errors import UnauthorizedError


def _verify(provided: Optional[str]) -> None:
    if not provided or not hmac.compare_digest(provided, config.api_key):
        raise UnauthorizedError("Missing or invalid API key")


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    _verify(x_api_key)


def require_api_key_header_or_query(
    x_api_key: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None, alias="apiKey"),
) -> None:
    # Browser EventSource and <img> requests cannot set headers, so these endpoints also accept ?apiKey=.
    _verify(x_api_key or api_key)
