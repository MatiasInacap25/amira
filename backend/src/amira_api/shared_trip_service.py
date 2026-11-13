"""Shared trips: publishing a paid service as a trip, closing it, and linking a paid join request at payment.

A trip is a route (origin stop, destination stop) with one vehicle and its driver. Every service on the trip must have
a trip vehicle, so publishing always assigns one. Capacity is not calculated: the provider decides per request, and
closing the trip only stops new requests. Services already linked, or already accepted when the trip closes, stay linked.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from amira_api.driver_verification import is_driver_verified
from amira_api.models import Conductor, ParadaViaje, RolUsuario, Servicio, Usuario, Vehiculo, Viaje, ViajeVehiculo

TRIP_STATUS_SCHEDULED = "scheduled"
# Stop orders are unique per trip and must stay positive. Existing stops move to this offset while the route is renumbered.
_RENUMBER_OFFSET = 1000


class SharedTripConflict(Exception):
    """The trip or service is not in a state that allows the operation. The message is user-facing Spanish."""


def provider_drivers_query(profile_id: UUID, owner_account_id: UUID):
    """Drivers the caller may put on a trip: a company's own employed drivers, or the caller's own driver record."""
    return (
        select(Conductor.id, Usuario.first_name, Usuario.last_name)
        .join(Usuario, Usuario.id == Conductor.user_id)
        .join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .where(
            or_(
                and_(Conductor.employer_profile_id == profile_id, RolUsuario.code == "company_driver"),
                and_(
                    Conductor.user_id == owner_account_id,
                    or_(Conductor.employer_profile_id.is_(None), Conductor.employer_profile_id == profile_id),
                ),
            )
        )
    )


def publish_shared_trip(
    session: Session,
    *,
    service: Servicio,
    vehicle: Vehiculo,
    driver: Conductor,
    now: datetime,
) -> Viaje:
    """Create the trip from a paid service: origin and destination stops, the trip vehicle, and the service's link."""
    if service.is_exclusive:
        raise SharedTripConflict("El cliente no aceptó compartir este viaje.")
    if service.trip_id is not None:
        raise SharedTripConflict("Este servicio ya tiene un viaje compartido.")
    form = service.form
    if form.requested_at is None:
        raise SharedTripConflict("El servicio necesita una fecha para publicar el viaje.")
    if not form.origin or not form.destination:
        raise SharedTripConflict("El servicio necesita origen y destino para publicar el viaje.")
    if not is_driver_verified(session, driver.user_id):
        raise SharedTripConflict("El conductor debe tener sus certificados verificados para publicar el viaje.")

    trip = Viaje(
        id=uuid4(),
        profile_id=service.profile_id,
        registered_at=now,
        origin=form.origin,
        destination=form.destination,
        origin_commune_code=form.origin_commune_code,
        destination_commune_code=form.destination_commune_code,
        status=TRIP_STATUS_SCHEDULED,
        departure_at=form.requested_at,
        is_published=True,
        accepts_requests=True,
    )
    session.add(trip)
    session.flush()
    session.add(ViajeVehiculo(trip_id=trip.id, vehicle_id=vehicle.id, driver_id=driver.id))
    origin_stop = ParadaViaje(id=uuid4(), trip_id=trip.id, order=1, address=form.origin)
    destination_stop = ParadaViaje(id=uuid4(), trip_id=trip.id, order=2, address=form.destination)
    session.add_all([origin_stop, destination_stop])
    session.flush()

    service.trip_id = trip.id
    service.vehicle_id = vehicle.id
    service.pickup_stop_id = origin_stop.id
    service.delivery_stop_id = destination_stop.id
    session.flush()
    return trip


def close_shared_trip(trip: Viaje) -> None:
    """Stop new requests. Services already linked to the trip, and requests already accepted, keep their link."""
    trip.accepts_requests = False


def link_join_request_stops(
    session: Session,
    *,
    trip_id: UUID,
    pickup_address: str,
    delivery_address: str,
    is_exclusive: bool,
) -> tuple[Viaje, Vehiculo, ParadaViaje, ParadaViaje]:
    """Insert the joined service's pickup and delivery stops before the trip destination, under the trip row lock.

    The route becomes: existing stops in order, then pickup, then delivery, then the original destination, numbered
    1..n. Returns the trip, its vehicle and the new pickup and delivery stops. An exclusive service never gets stops.
    """
    if is_exclusive:
        raise SharedTripConflict("El cliente no aceptó compartir este viaje.")
    trip = session.execute(select(Viaje).where(Viaje.id == trip_id).with_for_update()).scalar_one_or_none()
    if trip is None:
        raise SharedTripConflict("El viaje compartido ya no está disponible; el pago no se aplicó.")
    assignment = session.execute(
        select(ViajeVehiculo).where(ViajeVehiculo.trip_id == trip.id).order_by(ViajeVehiculo.vehicle_id).limit(1)
    ).scalar_one_or_none()
    if assignment is None:
        raise SharedTripConflict("El viaje compartido no tiene vehículo asignado; el pago no se aplicó.")
    stops = session.execute(
        select(ParadaViaje).where(ParadaViaje.trip_id == trip.id).order_by(ParadaViaje.order)
    ).scalars().all()
    if len(stops) < 2:
        raise SharedTripConflict("El viaje compartido no tiene paradas de origen y destino; el pago no se aplicó.")
    vehicle = session.get(Vehiculo, assignment.vehicle_id)

    route_before, destination_stop = stops[:-1], stops[-1]
    pickup = ParadaViaje(id=uuid4(), trip_id=trip.id, order=_RENUMBER_OFFSET + len(stops), address=pickup_address)
    delivery = ParadaViaje(id=uuid4(), trip_id=trip.id, order=_RENUMBER_OFFSET + len(stops) + 1, address=delivery_address)
    session.add_all([pickup, delivery])
    # Two phases keep (trip, order) unique: first move every existing stop out of the final range, then number the route.
    for index, stop in enumerate(stops):
        stop.order = _RENUMBER_OFFSET + index
    session.flush()
    route = [*route_before, pickup, delivery, destination_stop]
    for number, stop in enumerate(route, start=1):
        stop.order = number
    session.flush()
    return trip, vehicle, pickup, delivery
