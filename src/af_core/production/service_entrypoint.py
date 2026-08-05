from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence

from .configuration import ProductionSettings
from .service_host import ProductionServiceHost
from .service_host_models import ServiceHostSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="af-core-service",
        description=(
            "Run the AF-Core production service host "
            "with lifecycle, probes, metrics, and "
            "signal-aware shutdown."
        ),
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Validate production and service-host "
            "configuration without starting the service."
        ),
    )

    parser.add_argument(
        "--print-config",
        action="store_true",
        help=(
            "Print the credential-free effective "
            "configuration as JSON."
        ),
    )

    return parser


def load_settings() -> tuple[
    ProductionSettings,
    ServiceHostSettings,
]:
    source = dict(os.environ)

    production_source = {
        key: value
        for key, value in source.items()
        if not key.startswith("AF_CORE_HOST_")
    }

    return (
        ProductionSettings.from_environment(
            production_source
        ),
        ServiceHostSettings.from_environment(
            source
        ),
    )


def public_configuration(
    production_settings: ProductionSettings,
    host_settings: ServiceHostSettings,
) -> dict[str, object]:
    return {
        "production": (
            production_settings.public_snapshot()
        ),
        "service_host": (
            host_settings.public_snapshot()
        ),
    }


async def run_service(
    production_settings: ProductionSettings,
    host_settings: ServiceHostSettings,
) -> None:
    host = ProductionServiceHost(
        production_settings,
        host_settings,
        manage_signals=True,
    )

    await host.run()


def main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        production_settings, host_settings = (
            load_settings()
        )
    except Exception as exc:
        print(
            f"AF-Core configuration error: {exc}",
            file=sys.stderr,
        )
        return 2

    if arguments.print_config:
        print(
            json.dumps(
                public_configuration(
                    production_settings,
                    host_settings,
                ),
                indent=2,
                sort_keys=True,
            )
        )

    if arguments.check:
        print(
            "AF-Core production configuration: PASS"
        )

    if arguments.check or arguments.print_config:
        return 0

    try:
        asyncio.run(
            run_service(
                production_settings,
                host_settings,
            )
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(
            f"AF-Core service failure: {exc}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
