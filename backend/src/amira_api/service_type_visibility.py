"""Service types hidden from the catalog without touching stored data.

A hidden type keeps its ``Tipos_Servicio`` row, so every existing reference (services, quotations, requests, provider
links) stays valid. Hiding only removes the type from the public catalog, the public service filters and new provider
selections. No migration or data change is involved; the list lives here and nowhere else.
"""

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from amira_api.models import TipoServicio

HIDDEN_SERVICE_TYPE_SLUGS: frozenset[str] = frozenset({"carga-compartida"})


# Scalar comparisons instead of IN/NOT IN: the compiled statement then carries plain values, not list parameters.
def hidden_service_type_clause() -> ColumnElement[bool]:
    """SQL condition matching hidden service types; usable in ``where`` and ``filter`` clauses."""
    return or_(*(TipoServicio.slug == slug for slug in sorted(HIDDEN_SERVICE_TYPE_SLUGS)))


def visible_service_type_clause() -> ColumnElement[bool]:
    """SQL condition matching service types that are not hidden."""
    return and_(*(TipoServicio.slug != slug for slug in sorted(HIDDEN_SERVICE_TYPE_SLUGS)))
