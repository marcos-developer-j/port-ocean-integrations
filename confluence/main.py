from enum import StrEnum
from typing import Any, AsyncGenerator

from loguru import logger
from port_ocean.context.ocean import ocean

from client import ConfluenceClient
from converter import enrich_page_with_markdown


class ObjectKind(StrEnum):
    SPACE = "space"
    PAGE = "page"


def create_client() -> ConfluenceClient:
    """Crea el cliente de Confluence con la configuración de la integración."""
    return ConfluenceClient(
        base_url=ocean.integration_config["confluence_base_url"],
        username=ocean.integration_config["confluence_username"],
        api_token=ocean.integration_config["confluence_api_token"],
        page_size=int(ocean.integration_config.get("page_size", 50)),
    )


@ocean.on_resync(ObjectKind.SPACE)
async def resync_spaces(kind: str) -> AsyncGenerator[list[dict[str, Any]], None]:
    """Sincroniza todos los espacios de Confluence."""
    client = create_client()
    async for batch in client.get_spaces():
        yield batch


@ocean.on_resync(ObjectKind.PAGE)
async def resync_pages(kind: str) -> AsyncGenerator[list[dict[str, Any]], None]:
    """
    Sincroniza todas las páginas de Confluence.

    Cada página se enriquece con:
    - Campo 'markdown': contenido convertido de HTML a Markdown
    - Campo '__space': referencia al espacio padre
    """
    client = create_client()
    base_url = ocean.integration_config["confluence_base_url"].rstrip("/")

    async for batch in client.get_pages():
        enriched_batch = []
        for page in batch:
            # Enriquecer con markdown
            page = enrich_page_with_markdown(page)

            # Agregar referencia al espacio para la relación
            page["__space"] = {
                "id": page.get("spaceId"),
            }

            # Construir URL completa de la página
            page["webUrl"] = f"{base_url}/wiki{page.get('_links', {}).get('webui', '')}"

            enriched_batch.append(page)

        yield enriched_batch


@ocean.on_start()
async def on_start() -> None:
    """Callback al iniciar la integración."""
    logger.info("Starting Port Ocean Confluence integration")
    logger.info(
        f"Confluence URL: {ocean.integration_config.get('confluence_base_url', 'not set')}"
    )
