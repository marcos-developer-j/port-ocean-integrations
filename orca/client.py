from typing import Any, AsyncGenerator

from loguru import logger
from port_ocean.utils import http_async_client

PAGE_SIZE = 500


class OrcaClient:
    def __init__(self, api_url: str, api_token: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.client = http_async_client
        self.client.headers.update({"Authorization": f"Token {api_token}"})

    async def _get_paginated(
        self, path: str
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        url = f"{self.api_url}{path}"
        next_page_token: str | None = None

        while True:
            params: dict[str, Any] = {"limit": PAGE_SIZE}
            if next_page_token:
                params["next_page_token"] = next_page_token

            logger.debug(f"Fetching {url} with params {params}")
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

            data = payload.get("data")
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = [data]
            else:
                # Fallback: some endpoints return items under other keys
                fallback = payload.get("alerts") or payload.get("assets")
                items = fallback if isinstance(fallback, list) else []

            logger.info(f"Fetched {len(items)} items from {path}")
            yield items

            next_page_token = payload.get("next_page_token")
            if not next_page_token:
                break

    async def get_assets(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        async for batch in self._get_paginated("/api/assets"):
            yield batch

    async def get_alerts(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        async for batch in self._get_paginated("/api/alerts"):
            yield batch
