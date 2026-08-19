from typing import Literal

from port_ocean.core.handlers.port_app_config.api import APIPortAppConfig
from port_ocean.core.handlers.port_app_config.models import (
    PortAppConfig,
    ResourceConfig,
    Selector,
)
from port_ocean.core.integrations.base import BaseIntegration
from pydantic import Field


class VeracodeFindingSelector(Selector):
    scan_types: list[str] = Field(
        alias="scanTypes",
        default=["STATIC", "SCA"],
        description="Veracode scan types to ingest findings for "
        "(STATIC, DYNAMIC, SCA, MANUAL)",
    )


class VeracodeFindingResourceConfig(ResourceConfig):
    kind: Literal["finding"]
    selector: VeracodeFindingSelector


class VeracodePortAppConfig(PortAppConfig):
    resources: list[VeracodeFindingResourceConfig | ResourceConfig] = Field(
        default_factory=list
    )


class VeracodeIntegration(BaseIntegration):
    class AppConfigHandlerClass(APIPortAppConfig):
        CONFIG_CLASS = VeracodePortAppConfig
