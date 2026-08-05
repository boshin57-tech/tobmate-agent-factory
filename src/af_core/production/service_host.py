"""Official AF-Core production service host."""

from __future__ import annotations

import asyncio

from .configuration import ProductionSettings
from .health import (
    HealthRegistry,
    ServiceRuntimeHealthAdapter,
)
from .metrics import (
    MetricsRegistry,
    ServiceRuntimeMetricsAdapter,
)
from .probe_http import (
    ProbeResponse,
    ServiceProbeApplication,
)
from .service_host_models import (
    ServiceHostSettings,
    ServiceHostShutdownError,
    ServiceHostSnapshot,
    ServiceHostStartupError,
    ServiceHostState,
)
from .service_runtime import (
    ServiceResource,
    ServiceRuntime,
)
from .signals import SignalShutdownController


_STATUS_TEXT = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    413: "Content Too Large",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


class ProductionServiceHost:
    """Compose AF-Core production lifecycle components."""

    def __init__(
        self,
        production_settings: ProductionSettings,
        host_settings: ServiceHostSettings,
        *,
        runtime: ServiceRuntime | None = None,
        health: HealthRegistry | None = None,
        metrics: MetricsRegistry | None = None,
        probe_application: ServiceProbeApplication | None = None,
        signal_controller: SignalShutdownController | None = None,
        manage_signals: bool = True,
    ) -> None:
        self._production_settings = production_settings
        self._host_settings = host_settings

        self._runtime = (
            runtime
            if runtime is not None
            else ServiceRuntime(
                shutdown_timeout_seconds=(
                    host_settings.shutdown_timeout_seconds
                )
            )
        )

        self._health = (
            health
            if health is not None
            else HealthRegistry()
        )

        self._metrics = (
            metrics
            if metrics is not None
            else MetricsRegistry()
        )

        self._health_adapter = (
            ServiceRuntimeHealthAdapter(
                self._runtime
            )
        )

        registered = set(
            self._health.registered_names
        )

        for check in self._health_adapter.checks():
            if check.name not in registered:
                self._health.register(check)
                registered.add(check.name)

        self._metrics_adapter = (
            ServiceRuntimeMetricsAdapter(
                self._runtime,
                self._metrics,
            )
        )

        self._probe_application = (
            probe_application
            if probe_application is not None
            else ServiceProbeApplication(
                self._health,
                self._metrics,
                service_name=(
                    production_settings.service_name
                ),
            )
        )

        self._manage_signals = manage_signals

        self._signal_controller = (
            signal_controller
            if signal_controller is not None
            else SignalShutdownController(
                self._runtime
            )
        )

        self._state = ServiceHostState.CREATED
        self._server: asyncio.AbstractServer | None = None
        self._bound_probe_host: str | None = None
        self._bound_probe_port: int | None = None
        self._shutdown_reason: str | None = None
        self._lifecycle_lock = asyncio.Lock()

        if self._host_settings.probe_enabled:
            self._runtime.register(
                ServiceResource(
                    name="probe-http",
                    start=self._start_probe_server,
                    stop=self._stop_probe_server,
                    required=True,
                )
            )

    @property
    def state(self) -> ServiceHostState:
        """Return the current host state."""

        return self._state

    @property
    def runtime(self) -> ServiceRuntime:
        """Return the composed service runtime."""

        return self._runtime

    @property
    def health(self) -> HealthRegistry:
        """Return the composed health registry."""

        return self._health

    @property
    def metrics(self) -> MetricsRegistry:
        """Return the composed metrics registry."""

        return self._metrics

    @property
    def probe_application(
        self,
    ) -> ServiceProbeApplication:
        """Return the probe application."""

        return self._probe_application

    @property
    def bound_probe_address(
        self,
    ) -> tuple[str, int] | None:
        """Return the actual bound probe address."""

        if (
            self._bound_probe_host is None
            or self._bound_probe_port is None
        ):
            return None

        return (
            self._bound_probe_host,
            self._bound_probe_port,
        )

    def snapshot(self) -> ServiceHostSnapshot:
        """Return a credential-free immutable host snapshot."""

        runtime_state = getattr(
            self._runtime.state,
            "value",
            str(self._runtime.state),
        )

        return ServiceHostSnapshot(
            state=self._state,
            service_name=(
                self._production_settings.service_name
            ),
            instance_id=(
                self._production_settings.instance_id
            ),
            runtime_state=runtime_state,
            probe_enabled=(
                self._host_settings.probe_enabled
            ),
            configured_probe_host=(
                self._host_settings.probe_host
            ),
            configured_probe_port=(
                self._host_settings.probe_port
            ),
            bound_probe_host=(
                self._bound_probe_host
            ),
            bound_probe_port=(
                self._bound_probe_port
            ),
            signal_controller_installed=(
                self._signal_controller.installed
            ),
            shutdown_reason=(
                self._shutdown_reason
            ),
        )

    def request_shutdown(
        self,
        reason: str = "requested",
    ) -> None:
        """Request bounded runtime shutdown."""

        normalized = reason.strip()

        if not normalized:
            raise ServiceHostShutdownError(
                "shutdown reason must not be empty"
            )

        self._shutdown_reason = normalized
        self._runtime.request_shutdown(
            normalized
        )

    async def start(
        self,
    ) -> ServiceHostSnapshot:
        """Start all required production resources."""

        async with self._lifecycle_lock:
            if self._state is ServiceHostState.RUNNING:
                return self.snapshot()

            if self._state is not ServiceHostState.CREATED:
                raise ServiceHostStartupError(
                    "service host cannot start from "
                    f"state {self._state.value}"
                )

            self._state = ServiceHostState.STARTING

            try:
                if (
                    self._manage_signals
                    and not self._signal_controller.installed
                ):
                    self._signal_controller.install()

                await self._runtime.start()
                self._metrics_adapter.observe()

            except BaseException as exc:
                self._state = ServiceHostState.FAILED

                if (
                    self._manage_signals
                    and self._signal_controller.installed
                ):
                    try:
                        self._signal_controller.uninstall()
                    except Exception:
                        pass

                raise ServiceHostStartupError(
                    "production service host "
                    "failed to start"
                ) from exc

            self._state = ServiceHostState.RUNNING
            return self.snapshot()

    async def stop(
        self,
        *,
        reason: str = "requested",
    ) -> ServiceHostSnapshot:
        """Stop all resources within the configured timeout."""

        normalized = reason.strip()

        if not normalized:
            raise ServiceHostShutdownError(
                "shutdown reason must not be empty"
            )

        async with self._lifecycle_lock:
            if self._state is ServiceHostState.STOPPED:
                return self.snapshot()

            self._shutdown_reason = normalized

            if self._state is ServiceHostState.CREATED:
                self._state = ServiceHostState.STOPPED
                return self.snapshot()

            if self._state is ServiceHostState.STOPPING:
                return self.snapshot()

            self._state = ServiceHostState.STOPPING

            try:
                await self._runtime.stop(
                    reason=normalized,
                    timeout_seconds=(
                        self._host_settings
                        .shutdown_timeout_seconds
                    ),
                )

                self._metrics_adapter.observe()

            except BaseException as exc:
                self._state = ServiceHostState.FAILED

                raise ServiceHostShutdownError(
                    "production service host "
                    "failed to stop"
                ) from exc

            finally:
                if (
                    self._manage_signals
                    and self._signal_controller.installed
                ):
                    self._signal_controller.uninstall()

            self._state = ServiceHostState.STOPPED
            return self.snapshot()

    async def run(
        self,
    ) -> ServiceHostSnapshot:
        """Run until a signal or explicit shutdown request."""

        await self.start()

        try:
            reason = await self._runtime.wait_for_shutdown()
        except BaseException:
            await self.stop(
                reason="host-run-failure"
            )
            raise

        return await self.stop(
            reason=reason,
        )

    async def __aenter__(
        self,
    ) -> "ProductionServiceHost":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        reason = (
            "context-error"
            if exc is not None
            else "context-exit"
        )

        await self.stop(
            reason=reason,
        )

    async def _start_probe_server(
        self,
    ) -> None:
        """Bind the bounded local HTTP probe server."""

        if self._server is not None:
            return

        try:
            server = await asyncio.start_server(
                self._handle_probe_client,
                host=self._host_settings.probe_host,
                port=self._host_settings.probe_port,
                backlog=self._host_settings.backlog,
                limit=(
                    self._host_settings
                    .maximum_request_bytes
                ),
            )

        except OSError as exc:
            raise ServiceHostStartupError(
                "probe HTTP server could not bind"
            ) from exc

        sockets = tuple(server.sockets or ())

        if not sockets:
            server.close()
            await server.wait_closed()

            raise ServiceHostStartupError(
                "probe HTTP server has no bound socket"
            )

        address = sockets[0].getsockname()

        if (
            not isinstance(address, tuple)
            or len(address) < 2
        ):
            server.close()
            await server.wait_closed()

            raise ServiceHostStartupError(
                "probe HTTP socket address is invalid"
            )

        bound_host = str(address[0])
        bound_port = int(address[1])

        if bound_port < 1:
            server.close()
            await server.wait_closed()

            raise ServiceHostStartupError(
                "probe HTTP socket port is invalid"
            )

        self._server = server
        self._bound_probe_host = bound_host
        self._bound_probe_port = bound_port

    async def _stop_probe_server(
        self,
    ) -> None:
        """Stop accepting probe requests and release the socket."""

        server = self._server

        self._server = None
        self._bound_probe_host = None
        self._bound_probe_port = None

        if server is None:
            return

        server.close()

        try:
            await server.wait_closed()

        except OSError as exc:
            raise ServiceHostShutdownError(
                "probe HTTP server failed to close"
            ) from exc

    async def _handle_probe_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle one bounded HTTP probe connection."""

        response: ProbeResponse

        try:
            method, path = await asyncio.wait_for(
                self._read_probe_request(reader),
                timeout=(
                    self._host_settings
                    .request_timeout_seconds
                ),
            )

            self._metrics_adapter.observe()

            response = await self._probe_application.handle(
                method,
                path,
            )

        except TimeoutError:
            response = self._error_response(
                408,
                b'{"error":"request timeout"}',
            )

        except asyncio.LimitOverrunError:
            response = self._error_response(
                413,
                b'{"error":"request too large"}',
            )

        except (
            asyncio.IncompleteReadError,
            UnicodeError,
            ValueError,
        ):
            response = self._error_response(
                400,
                b'{"error":"bad request"}',
            )

        except Exception:
            response = self._error_response(
                500,
                b'{"error":"internal server error"}',
            )

        await self._write_probe_response(
            writer,
            response,
        )

    async def _read_probe_request(
        self,
        reader: asyncio.StreamReader,
    ) -> tuple[str, str]:
        """Read and validate one header-only HTTP request."""

        payload = await reader.readuntil(
            b"\r\n\r\n"
        )

        if (
            len(payload)
            > self._host_settings.maximum_request_bytes
        ):
            raise asyncio.LimitOverrunError(
                "probe request is too large",
                len(payload),
            )

        lines = payload.split(b"\r\n")

        if not lines or not lines[0]:
            raise ValueError(
                "probe request line is missing"
            )

        request_line = lines[0].decode(
            "ascii",
            errors="strict",
        )

        parts = request_line.split(" ")

        if len(parts) != 3:
            raise ValueError(
                "probe request line is invalid"
            )

        method, path, protocol = parts

        if protocol not in {
            "HTTP/1.0",
            "HTTP/1.1",
        }:
            raise ValueError(
                "probe HTTP version is unsupported"
            )

        if (
            not method
            or not method.isalpha()
            or not method.isascii()
        ):
            raise ValueError(
                "probe HTTP method is invalid"
            )

        if (
            not path.startswith("/")
            or len(path) > 2048
            or "\x00" in path
        ):
            raise ValueError(
                "probe HTTP path is invalid"
            )

        for raw_header in lines[1:]:
            if not raw_header:
                continue

            if b":" not in raw_header:
                raise ValueError(
                    "probe HTTP header is invalid"
                )

            name, value = raw_header.split(
                b":",
                1,
            )

            header_name = name.decode(
                "ascii",
                errors="strict",
            ).strip().lower()

            header_value = value.decode(
                "ascii",
                errors="strict",
            ).strip()

            if not header_name:
                raise ValueError(
                    "probe HTTP header name is empty"
                )

            if header_name == "content-length":
                length = int(header_value)

                if length != 0:
                    raise ValueError(
                        "probe request body is prohibited"
                    )

            if header_name == "transfer-encoding":
                raise ValueError(
                    "probe transfer encoding is prohibited"
                )

        return method.upper(), path

    @staticmethod
    def _error_response(
        status_code: int,
        body: bytes,
    ) -> ProbeResponse:
        """Create one bounded JSON error response."""

        return ProbeResponse(
            status_code=status_code,
            content_type="application/json",
            body=body,
            headers=(),
        )

    async def _write_probe_response(
        self,
        writer: asyncio.StreamWriter,
        response: ProbeResponse,
    ) -> None:
        """Write one HTTP response and always close the connection."""

        status_code = response.status_code

        if not 100 <= status_code <= 599:
            status_code = 500
            response = self._error_response(
                500,
                b'{"error":"invalid response status"}',
            )

        reason = _STATUS_TEXT.get(
            status_code,
            "Status",
        )

        headers: list[tuple[str, str]] = [
            (
                "Content-Type",
                response.content_type,
            ),
            (
                "Content-Length",
                str(len(response.body)),
            ),
            (
                "Connection",
                "close",
            ),
            (
                "Cache-Control",
                "no-store",
            ),
            (
                "X-Content-Type-Options",
                "nosniff",
            ),
        ]

        protected_headers = {
            "content-type",
            "content-length",
            "connection",
        }

        for name, value in response.headers:
            normalized_name = name.strip()
            normalized_value = value.strip()

            if (
                not normalized_name
                or normalized_name.lower()
                in protected_headers
            ):
                continue

            if not all(
                character.isalnum()
                or character == "-"
                for character in normalized_name
            ):
                continue

            if (
                "\r" in normalized_value
                or "\n" in normalized_value
            ):
                continue

            try:
                normalized_name.encode("ascii")
                normalized_value.encode("ascii")
            except UnicodeEncodeError:
                continue

            headers.append(
                (
                    normalized_name,
                    normalized_value,
                )
            )

        head = [
            f"HTTP/1.1 {status_code} {reason}\r\n"
        ]

        head.extend(
            f"{name}: {value}\r\n"
            for name, value in headers
        )

        head.append("\r\n")

        payload = (
            "".join(head).encode("ascii")
            + response.body
        )

        try:
            writer.write(payload)

            await asyncio.wait_for(
                writer.drain(),
                timeout=(
                    self._host_settings
                    .request_timeout_seconds
                ),
            )

        except (
            ConnectionError,
            OSError,
            TimeoutError,
        ):
            pass

        finally:
            writer.close()

            try:
                await writer.wait_closed()
            except (
                ConnectionError,
                OSError,
            ):
                pass
