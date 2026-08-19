from enum import StrEnum
from typing import Any, AsyncGenerator

from fastapi import Request
from loguru import logger
from port_ocean.context.ocean import ocean

from client import OrcaClient


class ObjectKind(StrEnum):
    ASSET = "asset"
    ALERT = "alert"


def create_client() -> OrcaClient:
    return OrcaClient(
        ocean.integration_config["orca_api_url"],
        ocean.integration_config["orca_api_token"],
    )


@ocean.on_resync(ObjectKind.ASSET)
async def on_resync_assets(kind: str) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for batch in client.get_assets():
        yield batch


@ocean.on_resync(ObjectKind.ALERT)
async def on_resync_alerts(kind: str) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for batch in client.get_alerts():
        yield batch


@ocean.router.post("/webhook")
async def handle_webhook(request: Request) -> dict[str, Any]:
    payload = await request.json()
    data = payload.get("alert", payload)
    if isinstance(data, dict) and data.get("state"):
        await ocean.register_raw(ObjectKind.ALERT, [data])
        logger.info(f"Registered Orca alert {data.get('state', {}).get('alert_id')}")
    else:
        logger.warning("Received Orca webhook payload without alert state; skipping")
    return {"ok": True}


@ocean.on_start()
async def on_start() -> None:
    logger.info("Starting Port Ocean Orca Security integration")
