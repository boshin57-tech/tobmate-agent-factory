from __future__ import annotations

import asyncio
from types import SimpleNamespace

from af_core.tools.tool_anomaly_detection import (
    LifecycleRegistryInstallationRequestResolver,
    LifecycleToolQuarantineAdapter,
    ToolAnomalyAction,
    ToolAnomalyEvaluation,
    ToolAnomalySeverity,
)
from af_core.tools.tool_usage_analytics import (
    ToolAnalyticsKey,
)


class FakeLifecycleRegistry:
    def __init__(self) -> None:
        self._cases = {}


class FakeLifecycleOrchestrator:
    def __init__(
        self,
        lifecycle: FakeLifecycleRegistry,
    ) -> None:
        self.lifecycle = lifecycle

    def quarantine(
        self,
        *,
        request_id: str,
        reason: str,
    ):
        case = self.lifecycle._cases[
            request_id
        ]

        case.state = "QUARANTINED"
        case.quarantined_reason = reason

        return case


def test_lifecycle_registry_resolver_finds_active_request() -> None:
    lifecycle = FakeLifecycleRegistry()

    lifecycle._cases["request-old"] = (
        SimpleNamespace(
            request=SimpleNamespace(
                request_id="request-old",
                ecosystem_id="tool.echo",
            ),
            state="REMOVED",
        )
    )

    lifecycle._cases["request-active"] = (
        SimpleNamespace(
            request=SimpleNamespace(
                request_id="request-active",
                ecosystem_id="tool.echo",
            ),
            state="INSTALLED",
        )
    )

    resolver = (
        LifecycleRegistryInstallationRequestResolver(
            lifecycle=lifecycle
        )
    )

    request_id = asyncio.run(
        resolver.resolve_request_id(
            tool_id="tool.echo"
        )
    )

    assert request_id == "request-active"


def test_lifecycle_adapter_reaches_quarantined_state() -> None:
    lifecycle = FakeLifecycleRegistry()

    lifecycle._cases["request-active"] = (
        SimpleNamespace(
            request=SimpleNamespace(
                request_id="request-active",
                ecosystem_id="tool.echo",
            ),
            state="INSTALLED",
            quarantined_reason=None,
        )
    )

    orchestrator = FakeLifecycleOrchestrator(
        lifecycle
    )

    resolver = (
        LifecycleRegistryInstallationRequestResolver(
            lifecycle=lifecycle
        )
    )

    adapter = LifecycleToolQuarantineAdapter(
        orchestrator=orchestrator,
        request_resolver=resolver,
    )

    evaluation = ToolAnomalyEvaluation(
        policy_id="anomaly.default",
        key=ToolAnalyticsKey(
            tool_id="tool.echo"
        ),
        sample_size=100,
        baseline_sample_size=100,
        anomalous=True,
        severity=(
            ToolAnomalySeverity.CRITICAL
        ),
        recommended_action=(
            ToolAnomalyAction.QUARANTINE
        ),
    )

    result = asyncio.run(
        adapter.quarantine(
            tool_id="tool.echo",
            reason="Critical anomaly",
            evaluation=evaluation,
        )
    )

    case = lifecycle._cases[
        "request-active"
    ]

    assert result.requested is True
    assert result.successful is True
    assert result.request_id == (
        "request-active"
    )
    assert result.lifecycle_state == (
        "QUARANTINED"
    )

    assert case.state == "QUARANTINED"
    assert case.quarantined_reason == (
        "Critical anomaly"
    )


import inspect
import runpy

from af_core.tools.tool_anomaly_detection import (
    LifecycleRegistryInstallationRequestResolver,
    LifecycleToolQuarantineAdapter,
)
from af_core.tools.tool_installation_lifecycle import (
    ToolLifecycleState,
)
from af_core.tools.ecosystem_models import (
    ToolInstallationState,
)


def _load_lifecycle_test_helpers():
    namespace = runpy.run_path(
        "tests/unit/"
        "test_tool_installation_lifecycle.py"
    )

    return (
        namespace["setup_orchestrator"],
        namespace["request_install"],
    )


def _call_with_supported_kwargs(
    callable_object,
    **candidates,
):
    signature = inspect.signature(
        callable_object
    )

    kwargs = {
        name: value
        for name, value in candidates.items()
        if name in signature.parameters
    }

    return callable_object(**kwargs)


def _approve_installation(
    lifecycle,
    *,
    request_id: str,
) -> None:
    approve = getattr(
        lifecycle,
        "approve",
        None,
    )

    if approve is None:
        raise AssertionError(
            "Lifecycle has no approve() method."
        )

    _call_with_supported_kwargs(
        approve,
        request_id=request_id,
        actor="security-reviewer",
        approver="security-reviewer",
        approved_by="security-reviewer",
        decided_by="security-reviewer",
        reason="Approved for anomaly E2E.",
        message="Approved for anomaly E2E.",
    )


def _build_installation_policy(
    *,
    evaluator,
    ecosystem,
    lifecycle,
    request_id: str,
):
    namespace = runpy.run_path(
        "tests/unit/"
        "test_tool_installation_lifecycle.py"
    )

    case = lifecycle.get(request_id)
    request = case.request
    ecosystem_id = request.ecosystem_id
    entry = ecosystem.get(ecosystem_id)

    helper_candidates = [
        (name, value)
        for name, value in namespace.items()
        if callable(value)
        and "policy" in name.casefold()
        and name not in {
            "_build_installation_policy",
        }
    ]

    helper_arguments = {
        "evaluator": evaluator,
        "ecosystem": ecosystem,
        "lifecycle": lifecycle,
        "request_id": request_id,
        "case": case,
        "request": request,
        "entry": entry,
        "ecosystem_entry": entry,
        "ecosystem_id": ecosystem_id,
        "tool_id": ecosystem_id,
    }

    helper_errors = []

    for helper_name, helper in helper_candidates:
        signature = inspect.signature(helper)

        kwargs = {
            name: helper_arguments[name]
            for name in signature.parameters
            if name in helper_arguments
        }

        missing = [
            name
            for name, parameter
            in signature.parameters.items()
            if (
                parameter.default
                is inspect.Parameter.empty
                and parameter.kind
                not in {
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                }
                and name not in kwargs
            )
        ]

        if missing:
            continue

        try:
            candidate = helper(**kwargs)
        except Exception as exc:
            helper_errors.append(
                f"{helper_name}: {exc}"
            )
            continue

        if inspect.isawaitable(candidate):
            continue

        try:
            evaluator.evaluate(
                entry=entry,
                policy=candidate,
            )
        except Exception as exc:
            helper_errors.append(
                f"{helper_name}: {exc}"
            )
            continue

        return candidate

    # Helper가 없거나 모두 부적합하면 evaluator 또는
    # orchestrator fixture에 저장된 정책 객체를 확인합니다.
    for source in (
        evaluator,
        getattr(evaluator, "policy", None),
    ):
        if source is None:
            continue

        for attribute in (
            "policy",
            "installation_policy",
            "default_policy",
            "_policy",
        ):
            candidate = getattr(
                source,
                attribute,
                None,
            )

            if candidate is None:
                continue

            try:
                evaluator.evaluate(
                    entry=entry,
                    policy=candidate,
                )
            except Exception as exc:
                helper_errors.append(
                    f"{attribute}: {exc}"
                )
                continue

            return candidate

    available_helpers = ", ".join(
        name
        for name, _ in helper_candidates
    ) or "none"

    details = (
        "; ".join(helper_errors)
        if helper_errors
        else "no compatible helper"
    )

    raise AssertionError(
        "Unable to create installation policy. "
        f"Available policy helpers: "
        f"{available_helpers}. Details: {details}"
    )


async def _install_with_orchestrator(
    orchestrator,
    *,
    request_id: str,
    policy,
):
    install = getattr(
        orchestrator,
        "install",
        None,
    )

    if install is None:
        raise AssertionError(
            "Orchestrator has no install() method."
        )

    result = _call_with_supported_kwargs(
        install,
        request_id=request_id,
        actor="installer",
        installed_by="installer",
        policy=policy,
    )

    if inspect.isawaitable(result):
        result = await result

    return result


def _installation_record(
    ecosystem,
    ecosystem_id: str,
):
    for method_name in (
        "installation",
        "get_installation",
        "installation_record",
    ):
        method = getattr(
            ecosystem,
            method_name,
            None,
        )

        if not callable(method):
            continue

        try:
            return method(ecosystem_id)
        except TypeError:
            try:
                return method(
                    ecosystem_id=ecosystem_id
                )
            except TypeError:
                continue

    entry = ecosystem.get(ecosystem_id)

    for attribute in (
        "installation",
        "installation_record",
    ):
        value = getattr(
            entry,
            attribute,
            None,
        )

        if value is not None:
            return value

    return entry


def test_actual_lifecycle_fixture_auto_quarantine_e2e() -> None:
    (
        setup_orchestrator,
        request_install,
    ) = _load_lifecycle_test_helpers()

    (
        ecosystem,
        lifecycle,
        backend,
        evaluator,
        orchestrator,
    ) = setup_orchestrator()

    del backend

    request_id = "request-anomaly-e2e"

    request_case = _call_with_supported_kwargs(
        request_install,
        lifecycle=lifecycle,
        request_id=request_id,
        require_approval=True,
    )

    # Helper가 Case를 반환하지 않아도 Lifecycle에 등록됩니다.
    del request_case

    _approve_installation(
        lifecycle,
        request_id=request_id,
    )

    installation_policy = (
        _build_installation_policy(
            evaluator=evaluator,
            ecosystem=ecosystem,
            lifecycle=lifecycle,
            request_id=request_id,
        )
    )

    asyncio.run(
        _install_with_orchestrator(
            orchestrator,
            request_id=request_id,
            policy=installation_policy,
        )
    )

    installed = lifecycle.get(request_id)

    assert installed.state is (
        ToolLifecycleState.INSTALLED
    )

    ecosystem_id = (
        installed.request.ecosystem_id
    )

    resolver = (
        LifecycleRegistryInstallationRequestResolver(
            lifecycle=lifecycle
        )
    )

    resolved_request_id = asyncio.run(
        resolver.resolve_request_id(
            tool_id=ecosystem_id
        )
    )

    assert resolved_request_id == request_id

    adapter = LifecycleToolQuarantineAdapter(
        orchestrator=orchestrator,
        request_resolver=resolver,
        actor="anomaly-monitor",
    )

    evaluation = ToolAnomalyEvaluation(
        policy_id="anomaly.default",
        key=ToolAnalyticsKey(
            tool_id=ecosystem_id
        ),
        sample_size=100,
        baseline_sample_size=100,
        anomalous=True,
        severity=(
            ToolAnomalySeverity.CRITICAL
        ),
        recommended_action=(
            ToolAnomalyAction.QUARANTINE
        ),
    )

    result = asyncio.run(
        adapter.quarantine(
            tool_id=ecosystem_id,
            reason=(
                "Automatic quarantine: "
                "critical failure-rate anomaly."
            ),
            evaluation=evaluation,
        )
    )

    quarantined = lifecycle.get(request_id)

    assert result.requested is True
    assert result.successful is True
    assert result.request_id == request_id
    assert result.lifecycle_state == (
        "QUARANTINED"
    )

    assert quarantined.state is (
        ToolLifecycleState.QUARANTINED
    )
    assert quarantined.quarantined_reason == (
        "Automatic quarantine: "
        "critical failure-rate anomaly."
    )

    installation = _installation_record(
        ecosystem,
        ecosystem_id,
    )

    installation_state = getattr(
        installation,
        "state",
        getattr(
            installation,
            "installation_state",
            None,
        ),
    )

    assert installation_state is (
        ToolInstallationState.DISABLED
    )
