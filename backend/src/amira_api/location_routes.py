"""Public, read-only catalog of Chilean regions and communes."""

import unicodedata
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.db import get_db_session
from amira_api.location_schemas import LocationCatalog, LocationCommune, LocationRegion
from amira_api.models import Commune, Region

router = APIRouter(prefix="/api", tags=["locations"])
CATALOG_CACHE_CONTROL = "public, max-age=3600"


def _spanish_sort_key(name: str) -> str:
    """Approximate Spanish collation: accents ignored, and ñ sorts between n and o."""
    folded = name.casefold().replace("ñ", "n~")
    decomposed = unicodedata.normalize("NFD", folded)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


@router.get("/locations", response_model=LocationCatalog)
def list_locations(
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
) -> LocationCatalog:
    rows = session.execute(
        select(
            Region.code.label("region_code"),
            Region.name.label("region_name"),
            Commune.code.label("commune_code"),
            Commune.name.label("commune_name"),
        )
        .select_from(Region)
        .outerjoin(Commune, Commune.region_code == Region.code)
        .order_by(Region.order.asc(), Region.code.asc())
    ).mappings().all()

    regions: dict[str, LocationRegion] = {}
    for row in rows:
        region = regions.get(row["region_code"])
        if region is None:
            region = LocationRegion(code=row["region_code"], name=row["region_name"], communes=[])
            regions[row["region_code"]] = region
        if row["commune_code"] is not None:
            region.communes.append(LocationCommune(code=row["commune_code"], name=row["commune_name"]))

    for region in regions.values():
        region.communes.sort(key=lambda commune: (_spanish_sort_key(commune.name), commune.code))

    response.headers["Cache-Control"] = CATALOG_CACHE_CONTROL
    return LocationCatalog(regions=list(regions.values()))
