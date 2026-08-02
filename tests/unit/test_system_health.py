from af_core.system_health import (
    SystemHealthValidator,
    HealthStatus,
)


def test_system_health_is_healthy():

    validator = (
        SystemHealthValidator()
    )

    report = (
        validator.validate()
    )

    assert (
        report.overall_status
        ==
        HealthStatus.HEALTHY
    )


    assert len(
        report.checks
    ) > 0


def test_all_components_pass():

    report = (
        SystemHealthValidator()
        .validate()
    )


    for check in report.checks:

        assert (
            check.status
            ==
            HealthStatus.HEALTHY
        )
