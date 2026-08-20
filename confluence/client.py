from typing import Any, AsyncGenerator

from loguru import logger
from port_ocean.utils import http_async_client


class ConfluenceClient:
    """Cliente para la API REST v2 de Confluence Cloud."""

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        page_size: int = 50,
    ):
        # base_url debe ser https://<sitio>.atlassian.net
        self.base_url = base_url.rstrip("/")
        self.api_v2 = f"{self.base_url}/wiki/api/v2"
        self.page_size = page_size
        self.client = http_async_client
        # Confluence Cloud usa Basic Auth con email + API token
        import base64
        credentials = base64.b64encode(f"{username}:{api_token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
        }

    async def _get(self, url: str, params: dict | None = None) -> dict:
        response = await self.client.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    async def get_spaces(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Obtiene todos los espacios con paginación por cursor."""
        cursor: str | None = None
        while True:
            params = {"limit": self.page_size}
            if cursor:
                params["cursor"] = cursor

            data = await self._get(f"{self.api_v2}/spaces", params)
            results = data.get("results") or []
            logger.info(f"Fetched {len(results)} spaces")
            if results:
                yield results

            # Paginación: _links.next contiene el cursor
            links = data.get("_links", {})
            next_link = links.get("next")
            if not next_link:
                return
            # Extraer cursor del next link
            import urllib.parse
            parsed = urllib.parse.urlparse(next_link)
            query_params = urllib.parse.parse_qs(parsed.query)
            cursor = query_params.get("cursor", [None])[0]
            if not cursor:
                return

    async def get_pages(
        self, space_id: str | None = None
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Obtiene páginas, opcionalmente filtradas por espacio."""
        cursor: str | None = None
        while True:
            params = {"limit": self.page_size, "body-format": "storage"}
            if space_id:
                params["space-id"] = space_id
            if cursor:
                params["cursor"] = cursor

            data = await self._get(f"{self.api_v2}/pages", params)
            results = data.get("results") or []
            logger.info(f"Fetched {len(results)} pages")
            if results:
                yield results

            links = data.get("_links", {})
            next_link = links.get("next")
            if not next_link:
                return
            import urllib.parse
            parsed = urllib.parse.urlparse(next_link)
            query_params = urllib.parse.parse_qs(parsed.query)
            cursor = query_params.get("cursor", [None])[0]
            if not cursor:
                return

    async def get_page_content(self, page_id: str) -> dict[str, Any]:
        """Obtiene una página específica con su contenido HTML."""
        return await self._get(
            f"{self.api_v2}/pages/{page_id}",
            params={"body-format": "storage"},
        )

    async def get_folders(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        """
        Obtiene 'folders' de Confluence.
        Nota: Confluence no tiene folders nativos como tal. Las páginas padre
        actúan como contenedores. Este método lista páginas que tienen hijos
        (actúan como folders).
        """
        cursor: str | None = None
        while True:
            params = {"limit": self.page_size}
            if cursor:
                params["cursor"] = cursor

            data = await self._get(f"{self.api_v2}/pages", params)
            results = data.get("results") or []

            # Filtrar páginas que tienen hijos (actúan como folders)
            folders = [
                page for page in results
                if page.get("childPosition") is not None or page.get("parentId") is None
            ]

            if folders:
                logger.info(f"Fetched {len(folders)} folder-like pages")
                yield folders

            links = data.get("_links", {})
            next_link = links.get("next")
            if not next_link:
                return
            import urllib.parse
            parsed = urllib.parse.urlparse(next_link)
            query_params = urllib.parse.parse_qs(parsed.query)
            cursor = query_params.get("cursor", [None])[0]
            if not cursor:
                return
