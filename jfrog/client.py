from typing import Any, AsyncGenerator

import httpx
from loguru import logger
from port_ocean.utils import http_async_client

PAGE_SIZE = 100


class JFrogClient:
    """Cliente HTTP async para la API de la plataforma JFrog (Artifactory, Access y Xray)."""

    def __init__(self, host_url: str, access_token: str) -> None:
        self.host_url = host_url.rstrip("/")
        self.client = http_async_client
        self.client.headers.update({"Authorization": f"Bearer {access_token}"})

    async def get_projects(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Obtiene los projects de JFrog (requiere licencia con soporte de projects)."""
        url = f"{self.host_url}/access/api/v1/projects"
        logger.info(f"Fetching JFrog projects from {url}")
        response = await self.client.get(url)
        if response.status_code in (403, 404):
            logger.warning(
                f"JFrog projects API not available (status {response.status_code}). "
                "Skipping projects resync."
            )
            return
        response.raise_for_status()
        projects: list[dict[str, Any]] = response.json()
        logger.info(f"Fetched {len(projects)} JFrog projects")
        for i in range(0, len(projects), PAGE_SIZE):
            yield projects[i : i + PAGE_SIZE]

    async def get_repositories(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Obtiene todos los repositorios de Artifactory."""
        url = f"{self.host_url}/artifactory/api/repositories"
        logger.info(f"Fetching JFrog repositories from {url}")
        response = await self.client.get(url)
        response.raise_for_status()
        repositories: list[dict[str, Any]] = response.json()
        logger.info(f"Fetched {len(repositories)} JFrog repositories")
        for i in range(0, len(repositories), PAGE_SIZE):
            yield repositories[i : i + PAGE_SIZE]

    async def get_builds(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Obtiene todos los builds registrados en Artifactory."""
        url = f"{self.host_url}/artifactory/api/build"
        logger.info(f"Fetching JFrog builds from {url}")
        response = await self.client.get(url)
        if response.status_code == 404:
            logger.warning("No builds found in JFrog (404). Skipping builds resync.")
            return
        response.raise_for_status()
        builds: list[dict[str, Any]] = response.json().get("builds", [])
        logger.info(f"Fetched {len(builds)} JFrog builds")
        for i in range(0, len(builds), PAGE_SIZE):
            yield builds[i : i + PAGE_SIZE]

    async def _get_local_repositories(self) -> list[dict[str, Any]]:
        url = f"{self.host_url}/artifactory/api/repositories"
        response = await self.client.get(url, params={"type": "local"})
        response.raise_for_status()
        return response.json()

    async def get_artifacts(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Obtiene los artefactos de todos los repositorios locales usando AQL, paginado."""
        local_repositories = await self._get_local_repositories()
        logger.info(
            f"Fetching artifacts from {len(local_repositories)} local repositories"
        )
        aql_url = f"{self.host_url}/artifactory/api/search/aql"
        for repository in local_repositories:
            repo_key = repository.get("key")
            if not repo_key:
                continue
            offset = 0
            while True:
                query = (
                    f'items.find({{"repo": "{repo_key}"}})'
                    '.include("repo","path","name","size","sha256","modified","created")'
                    '.sort({"$desc": ["modified"]})'
                    f".offset({offset}).limit({PAGE_SIZE})"
                )
                logger.debug(
                    f"Running AQL query for repository {repo_key} with offset {offset}"
                )
                response = await self.client.post(
                    aql_url,
                    content=query,
                    headers={"Content-Type": "text/plain"},
                )
                response.raise_for_status()
                results: list[dict[str, Any]] = response.json().get("results", [])
                if not results:
                    break
                logger.info(
                    f"Fetched {len(results)} artifacts from repository {repo_key} "
                    f"(offset {offset})"
                )
                yield results
                if len(results) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE

    async def get_xray_violations(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Obtiene las violaciones de Xray, paginadas. Si Xray no está disponible, termina sin error."""
        url = f"{self.host_url}/xray/api/v1/violations"
        page = 1
        while True:
            body = {
                "filters": {},
                "pagination": {
                    "order_by": "created",
                    "limit": PAGE_SIZE,
                    "offset": page,
                },
            }
            logger.info(f"Fetching JFrog Xray violations page {page}")
            response = await self.client.post(url, json=body)
            if response.status_code in (400, 403, 404):
                logger.warning(
                    f"JFrog Xray violations API not available "
                    f"(status {response.status_code}). Skipping Xray violations resync."
                )
                return
            response.raise_for_status()
            violations: list[dict[str, Any]] = response.json().get("violations", [])
            if not violations:
                break
            logger.info(f"Fetched {len(violations)} Xray violations on page {page}")
            yield violations
            if len(violations) < PAGE_SIZE:
                break
            page += 1
