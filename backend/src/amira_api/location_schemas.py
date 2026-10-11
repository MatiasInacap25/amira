"""Public response models for the Chilean region and commune catalog."""

from pydantic import BaseModel, ConfigDict


class LocationCommune(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str


class LocationRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    communes: list[LocationCommune]


class LocationCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regions: list[LocationRegion]
