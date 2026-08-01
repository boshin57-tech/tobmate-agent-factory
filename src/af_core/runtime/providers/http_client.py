from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderHTTPError(RuntimeError):
    """Raised when a provider HTTP request fails."""


@dataclass(frozen=True)
class JSONHTTPResponse:
    status_code: int
    headers: dict[str, str]
    payload: dict[str, Any]


class AsyncJSONHTTPClient:
    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float = 120.0,
    ) -> JSONHTTPResponse:
        return await asyncio.to_thread(
            self._request_sync,
            method=method,
            url=url,
            headers=headers or {},
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def _request_sync(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> JSONHTTPResponse:
        request_headers = {
            "Accept": "application/json",
            **headers,
        }

        body: bytes | None = None

        if payload is not None:
            body = json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8")
            request_headers.setdefault(
                "Content-Type",
                "application/json",
            )

        request = Request(
            url=url,
            data=body,
            headers=request_headers,
            method=method,
        )

        try:
            with urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                raw = response.read()
                status_code = response.status
                response_headers = dict(response.headers.items())
        except HTTPError as exc:
            raw = exc.read()
            detail = raw.decode(
                "utf-8",
                errors="replace",
            )
            raise ProviderHTTPError(
                f"HTTP {exc.code} from {url}: {detail}"
            ) from exc
        except URLError as exc:
            raise ProviderHTTPError(
                f"Provider connection failed for {url}: "
                f"{exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise ProviderHTTPError(
                f"Provider request timed out: {url}"
            ) from exc

        try:
            parsed = json.loads(
                raw.decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderHTTPError(
                f"Provider returned invalid JSON: {url}"
            ) from exc

        if not isinstance(parsed, dict):
            raise ProviderHTTPError(
                "Provider JSON response must be an object."
            )

        return JSONHTTPResponse(
            status_code=status_code,
            headers=response_headers,
            payload=parsed,
        )
