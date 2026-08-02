from af_core.monitoring.metrics_collector import (
    MetricsCollector,
)

from af_core.monitoring.monitoring_models import (
    ExecutionMetric,
    MetricType,
)

from af_core.monitoring.health_monitor import (
    HealthMonitor,
)



def test_metric_collection():

    collector = (
        MetricsCollector()
    )


    collector.record(
        ExecutionMetric(
            project_id="gsos",

            agent_id="spatial-agent",

            metric_type=
            MetricType.EXECUTION,

            value=120,

            unit="seconds",
        )
    )


    assert (
        collector.count()
        == 1
    )



def test_health_monitor():

    result = (
        HealthMonitor()
        .check(
            active_agents=5,
            active_workspaces=2,
        )
    )


    assert (
        result.status
        ==
        "healthy"
    )
