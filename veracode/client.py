from typing import Any, AsyncGenerator

import httpx
from loguru import logger
from port_ocean.utils import http_async_client

from hmac_auth import VeracodeHMACAuth

PAGE_SIZE = 100


class VeracodeClient:
    """Async client for the Veracode REST APIs using HMAC-signed requests.

    The HMAC signature depends on the request host, path (including query
    string), method and a timestamp/nonce, so authentication is passed
    per-request via httpx's `auth` parameter instead of static headers.
    """

    def __init__(self, base_url: str, api_id: str, api_secret: str):
        self.base_url = base_url.rstrip("/")
        self.auth = VeracodeHMACAuth(api_id, api_secret)
        self.client = http_async_client

    async def _get_paginated(
        self,
        path: str,
        embedded_key: str,
        params: dict[str, Any] | None = None,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Iterate over a paginated Veracode endpoint, yielding item batches."""
        query_params: dict[str, Any] = dict(params or {})
        query_params["size"] = PAGE_SIZE
        page = 0

        while True:
            query_params["page"] = page
            url = f"{self.base_url}{path}"
            response = await self.client.get(
                url, params=query_params, auth=self.auth
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("_embedded", {}).get(embedded_key, [])
            if items:
                yield items

            page_info = data.get("page", {})
            if page >= page_info.get("total_pages", 0) - 1:
                break
            page += 1

    async def get_applications(
        self,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Yield batches of Veracode application profiles."""
        async for applications in self._get_paginated(
            "/appsec/v1/applications", "applications"
        ):
            logger.info(f"Fetched batch of {len(applications)} applications")
            yield applications

    async def get_findings(
        self, app: dict[str, Any], scan_types: list[str]
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Yield batches of findings for an application, per scan type.

        Each finding is enriched with an `__application` key so entity
        mappings can build identifiers and relations to the parent app.
        """
        app_guid = app["guid"]
        app_name = app.get("profile", {}).get("name")

        for scan_type in scan_types:
            try:
                async for findings in self._get_paginated(
                    f"/appsec/v2/applications/{app_guid}/findings",
                    "findings",
                    params={"scan_type": scan_type},
                ):
                    enriched = [
                        {
                            **finding,
                            "__application": {
                                "guid": app_guid,
                                "name": app_name,
                            },
                        }
                        for finding in findings
                    ]
                    logger.info(
                        f"Fetched batch of {len(enriched)} {scan_type} "
                        f"findings for application {app_name} ({app_guid})"
                    )
                    yield enriched
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (403, 404):
                    logger.warning(
                        f"Skipping {scan_type} findings for application "
                        f"{app_name} ({app_guid}): received HTTP {status_code}"
                    )
                    continue
                logger.error(
                    f"HTTP error {status_code} fetching {scan_type} findings "
                    f"for application {app_name} ({app_guid}): {e}"
                )
                raise
