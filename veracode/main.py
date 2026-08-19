from enum import StrEnum
from typing import Any, AsyncGenerator

from loguru import logger
from port_ocean.context.event import event
from port_ocean.context.ocean import ocean

from client import VeracodeClient


class ObjectKind(StrEnum):
    APPLICATION = "application"
    FINDING = "finding"


def create_client() -> VeracodeClient:
    return VeracodeClient(
        ocean.integration_config["veracode_api_base"],
        ocean.integration_config["veracode_api_id"],
        ocean.integration_config["veracode_api_secret"],
    )


@ocean.on_resync(ObjectKind.APPLICATION)
async def on_resync_applications(
    kind: str,
) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for applications in client.get_applications():
        logger.info(f"Yielding {len(applications)} applications")
        yield applications


@ocean.on_resync(ObjectKind.FINDING)
async def on_resync_findings(
    kind: str,
) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    selector = event.resource_config.selector  # type: ignore[union-attr]
    scan_types = getattr(selector, "scan_types", ["STATIC", "SCA"])
    logger.info(f"Resyncing findings for scan types: {scan_types}")

    async for apps in client.get_applications():
        for app in apps:
            async for findings in client.get_findings(app, scan_types):
                yield findings


@ocean.on_start()
async def on_start() -> None:
    logger.info("Starting Port Ocean Veracode integration")
