"""Framework-neutral HTTP and ASGI health/metrics probes."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .health import (
    HealthEvaluation,
    HealthRegistry,
    HealthScope,
    HealthSnapshot,
    HealthStatus,
)
from .metrics import (
    MetricsRegistry,
    PROMETHEUS_CONTENT_TYPE,
)


JSON_CONTENT_TYPE = (
    "application/json; charset=utf-8"
)


@dataclass(frozen=True, slots=True)
class ProbeResponse:
    """Immutable HTTP probe response."""

    status_code: int
    content_type: str
    body: bytes
    headers: tuple[tuple[str, str], ...]

    def header(
        self,
        name: str,
    ) -> str | None:
        normalized = name.lower()

        for key, value in self.headers:
            if key.lower() == normalized:
                return value

        return None


class ServiceProbeApplication:
    """Expose startup, live, ready and metrics endpoints."""

    def __init__(
        self,
        health: HealthRegistry,
        metrics: MetricsRegistry,
        *,
        service_name: str = "af-core",
    ) -> None:
        normalized = service_name.strip()

        if not normalized:
            raise ValueError(
                "service_name must not be empty"
            )

        self.health = health
        self.metrics = metrics
        self.service_name = normalized

    async def handle(
        self,
        method: str,
        path: str,
    ) -> ProbeResponse:
        normalized_method = method.upper().strip()

        if normalized_method not in {
            "GET",
            "HEAD",
        }:
            return self._response(
                405,
                JSON_CONTENT_TYPE,
                self._json_bytes(
                    {
                        "error": "method_not_allowed",
                    }
                ),
                extra_headers=(
                    ("allow", "GET, HEAD"),
                ),
            )

        if path == "/health/startup":
            response = await self._health_scope(
                HealthScope.STARTUP
            )
        elif path == "/health/live":
            response = await self._health_scope(
                HealthScope.LIVENESS
            )
        elif path == "/health/ready":
            response = await self._health_scope(
                HealthScope.READINESS
            )
        elif path == "/health":
            response = await self._health_snapshot()
        elif path == "/metrics":
            response = self._response(
                200,
                PROMETHEUS_CONTENT_TYPE,
                self.metrics.render_prometheus().encode(
                    "utf-8"
                ),
            )
        else:
            response = self._response(
                404,
                JSON_CONTENT_TYPE,
                self._json_bytes(
                    {
                        "error": "not_found",
                    }
                ),
            )

        if normalized_method == "HEAD":
            return ProbeResponse(
                status_code=response.status_code,
                content_type=response.content_type,
                body=b"",
                headers=response.headers,
            )

        return response

    async def _health_scope(
        self,
        scope: HealthScope,
    ) -> ProbeResponse:
        evaluation = await self.health.evaluate(
            scope
        )

        return self._response(
            self._health_status_code(
                evaluation.status
            ),
            JSON_CONTENT_TYPE,
            self._json_bytes(
                self._evaluation_payload(
                    evaluation
                )
            ),
        )

    async def _health_snapshot(
        self,
    ) -> ProbeResponse:
        snapshot = await self.health.snapshot()

        return self._response(
            self._health_status_code(
                snapshot.overall
            ),
            JSON_CONTENT_TYPE,
            self._json_bytes(
                self._snapshot_payload(
                    snapshot
                )
            ),
        )

    def _evaluation_payload(
        self,
        evaluation: HealthEvaluation,
    ) -> dict[str, object]:
        return {
            "service": self.service_name,
            "scope": evaluation.scope.value,
            "status": evaluation.status.value,
            "checked_at": evaluation.checked_at,
            "checks": [
                self._check_payload(check)
                for check in evaluation.checks
            ],
        }

    def _snapshot_payload(
        self,
        snapshot: HealthSnapshot,
    ) -> dict[str, object]:
        return {
            "service": self.service_name,
            "status": snapshot.overall.value,
            "startup": snapshot.startup.value,
            "liveness": snapshot.liveness.value,
            "readiness": snapshot.readiness.value,
            "checked_at": snapshot.checked_at,
            "checks": [
                self._check_payload(check)
                for check in snapshot.checks
            ],
        }

    @staticmethod
    def _check_payload(
        check,
    ) -> dict[str, object]:
        # Public probes intentionally omit check.detail.
        # Callback details may contain operational secrets.
        return {
            "name": check.name,
            "status": check.status.value,
            "required": check.required,
            "scopes": [
                scope.value
                for scope in check.scopes
            ],
            "checked_at": check.checked_at,
            "duration_ms": check.duration_ms,
        }

    @staticmethod
    def _health_status_code(
        status: HealthStatus,
    ) -> int:
        if status is HealthStatus.UNHEALTHY:
            return 503

        return 200

    @staticmethod
    def _json_bytes(
        payload: dict[str, object],
    ) -> bytes:
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

    @staticmethod
    def _response(
        status_code: int,
        content_type: str,
        body: bytes,
        *,
        extra_headers: tuple[
            tuple[str, str],
            ...,
        ] = (),
    ) -> ProbeResponse:
        headers = (
            ("content-type", content_type),
            ("cache-control", "no-store"),
            ("x-content-type-options", "nosniff"),
            ("content-length", str(len(body))),
            *extra_headers,
        )

        return ProbeResponse(
            status_code=status_code,
            content_type=content_type,
            body=body,
            headers=headers,
        )

    async def __call__(
        self,
        scope,
        receive,
        send,
    ) -> None:
        """Serve one ASGI HTTP request."""

        if scope.get("type") != "http":
            raise RuntimeError(
                "ServiceProbeApplication only "
                "supports ASGI HTTP scopes"
            )

        while True:
            event = await receive()

            if event.get("type") == "http.disconnect":
                return

            if (
                event.get("type") == "http.request"
                and not event.get(
                    "more_body",
                    False,
                )
            ):
                break

        response = await self.handle(
            scope.get("method", "GET"),
            scope.get("path", "/"),
        )

        encoded_headers = [
            (
                name.encode("latin-1"),
                value.encode("latin-1"),
            )
            for name, value in response.headers
        ]

        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": encoded_headers,
            }
        )

        await send(
            {
                "type": "http.response.body",
                "body": response.body,
                "more_body": False,
            }
        )
