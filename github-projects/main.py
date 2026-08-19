from enum import StrEnum
from typing import Any, AsyncGenerator

from loguru import logger
from port_ocean.context.ocean import ocean

from client import GithubProjectsClient


class ObjectKind(StrEnum):
    PROJECT = "project"
    PROJECT_ITEM = "project-item"


def create_client() -> GithubProjectsClient:
    # Los nombres camelCase del spec (githubGraphqlUrl) se acceden en snake_case
    return GithubProjectsClient(
        ocean.integration_config["github_graphql_url"],
        ocean.integration_config["github_token"],
        ocean.integration_config["github_organization"],
    )


@ocean.on_resync(ObjectKind.PROJECT)
async def resync_projects(kind: str) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for batch in client.get_projects():
        yield batch


@ocean.on_resync(ObjectKind.PROJECT_ITEM)
async def resync_project_items(
    kind: str,
) -> AsyncGenerator[list[dict[str, Any]], None]:
    client = create_client()
    async for projects in client.get_projects():
        for project in projects:
            async for items in client.get_project_items(project):
                yield items


@ocean.on_start()
async def on_start() -> None:
    logger.info("Starting Port Ocean GitHub Projects integration")
