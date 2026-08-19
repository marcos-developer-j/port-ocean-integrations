from typing import Any, AsyncGenerator

from loguru import logger
from port_ocean.utils import http_async_client

from queries import PROJECTS_QUERY, PROJECT_ITEMS_QUERY


class GithubProjectsClient:
    def __init__(self, graphql_url: str, token: str, organization: str):
        self.graphql_url = graphql_url
        self.organization = organization
        self.client = http_async_client
        self.headers = {"Authorization": f"Bearer {token}"}

    async def _execute(self, query: str, variables: dict) -> dict:
        response = await self.client.post(
            self.graphql_url,
            json={"query": query, "variables": variables},
            headers=self.headers,
        )
        response.raise_for_status()
        payload = response.json()
        if "errors" in payload:
            logger.error(f"GraphQL query returned errors: {payload['errors']}")
            raise Exception(f"GraphQL query returned errors: {payload['errors']}")
        return payload["data"]

    async def get_projects(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        cursor: str | None = None
        while True:
            data = await self._execute(
                PROJECTS_QUERY, {"org": self.organization, "cursor": cursor}
            )
            organization = data.get("organization")
            if organization is None:
                logger.warning(
                    f"Organization '{self.organization}' not found or token has no access"
                )
                return
            projects_page = organization["projectsV2"]
            nodes = projects_page.get("nodes") or []
            logger.info(f"Fetched {len(nodes)} projects from '{self.organization}'")
            yield nodes
            page_info = projects_page["pageInfo"]
            if not page_info["hasNextPage"]:
                return
            cursor = page_info["endCursor"]

    async def get_project_items(
        self, project: dict
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        cursor: str | None = None
        while True:
            data = await self._execute(
                PROJECT_ITEMS_QUERY, {"projectId": project["id"], "cursor": cursor}
            )
            node = data.get("node")
            if node is None:
                logger.warning(
                    f"Project node '{project['id']}' not found or inaccessible"
                )
                return
            items_page = node["items"]
            nodes = items_page.get("nodes") or []
            for item in nodes:
                item["__project"] = {
                    "id": project["id"],
                    "title": project.get("title"),
                    "number": project.get("number"),
                }
            logger.info(
                f"Fetched {len(nodes)} items from project '{project.get('title')}'"
            )
            yield nodes
            page_info = items_page["pageInfo"]
            if not page_info["hasNextPage"]:
                return
            cursor = page_info["endCursor"]
