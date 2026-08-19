from enum import StrEnum
from typing import Any, AsyncGenerator

from fastapi import Request
from loguru import logger
from port_ocean.context.ocean import ocean

from client import JFrogClient


class ObjectKind(StrEnum):
    PROJECT = "project"
    REPOSITORY = "repository"
    BUILD = "build"
    ARTIFACT = "artifact"
    XRAY_VIOLATION = "xray_violation"


def create_client() -> JFrogClient:
    return JFrogClient(
        ocean.integration_config["jfrog_host_url"],
        ocean.integration_config["jfrog_access_token"],
    )


@ocean.on_resync(ObjectKind.PROJECT)
async def on_resync_projects(kind: str) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for batch in client.get_projects():
        logger.info(f"Yielding batch of {len(batch)} projects")
        yield batch


@ocean.on_resync(ObjectKind.REPOSITORY)
async def on_resync_repositories(
    kind: str,
) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for batch in client.get_repositories():
        logger.info(f"Yielding batch of {len(batch)} repositories")
        yield batch


@ocean.on_resync(ObjectKind.BUILD)
async def on_resync_builds(kind: str) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for batch in client.get_builds():
        logger.info(f"Yielding batch of {len(batch)} builds")
        yield batch


@ocean.on_resync(ObjectKind.ARTIFACT)
async def on_resync_artifacts(kind: str) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for batch in client.get_artifacts():
        logger.info(f"Yielding batch of {len(batch)} artifacts")
        yield batch


@ocean.on_resync(ObjectKind.XRAY_VIOLATION)
async def on_resync_xray_violations(
    kind: str,
) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for batch in client.get_xray_violations():
        logger.info(f"Yielding batch of {len(batch)} Xray violations")
        yield batch


@ocean.router.post("/webhook")
async def handle_webhook(request: Request) -> dict[str, Any]:
    payload = await request.json()
    domain = payload.get("domain")
    logger.info(f"Received JFrog webhook event for domain: {domain}")
    data = payload.get("data", {})
    if domain == "artifact":
        await ocean.register_raw(
            ObjectKind.ARTIFACT,
            [
                {
                    "repo": data.get("repo_key"),
                    "path": data.get("path"),
                    "name": data.get("name"),
                    "size": data.get("size"),
                    "sha256": data.get("sha256"),
                }
            ],
        )
    elif domain == "build":
        await ocean.register_raw(
            ObjectKind.BUILD,
            [
                {
                    "uri": "/" + str(data.get("build_name", "")),
                    "lastStarted": data.get("build_started"),
                }
            ],
        )
    return {"ok": True}


@ocean.on_start()
async def on_start() -> None:
    logger.info("Starting Port Ocean JFrog integration")
